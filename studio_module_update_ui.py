"""Module update dialog: serialized background transfers, owner-thread activation."""
from PyQt6.QtCore import QThread, QTimer, Qt, pyqtSignal
from PyQt6.QtWidgets import QApplication, QDialog, QGridLayout, QHBoxLayout, QLabel, QProgressBar, QVBoxLayout

from v3_components import V3Button, ButtonVariant
from studio_module_updates import WorkflowUpdate, update_identity
from license_client import LicenseError, LicenseUnavailableError


MODULE_TITLES = {
    "clipart": "Генерация изображений",
    "processing": "Обработка изображений",
    "pinterest": "Pinterest",
    "auto-clipart": "Автоматический клипарт",
    "prompt-composer": "Конструктор промптов",
}


class ModuleUpdateWorker(QThread):
    progress = pyqtSignal(int, int)
    phase = pyqtSignal(str)

    def __init__(self, delivery, release=None, parent=None, authorization=None):
        super().__init__(parent)
        self.delivery = delivery
        self.release = release
        self.result = None
        self.failed = False
        self.authorization = None
        self.cancelled = False
        self.initial_authorization = authorization
        self.denied = False

    def cancel(self):
        # QThread clears its interruption flag when run() exits; retain intent
        # until the owner thread decides whether activation is still allowed.
        self.cancelled = True
        self.requestInterruption()

    def run(self):
        try:
            if self.release is not None:
                # Download grants expire. Refresh once on explicit user action,
                # but never substitute a different version for the selected one.
                fresh = self.delivery.check(self.release.module_id)
                if fresh is None or update_identity(fresh) != update_identity(self.release):
                    raise ValueError("Selected release changed")
                if (not isinstance(fresh, WorkflowUpdate)
                        and fresh.version in self.delivery.store.installed_versions(fresh.module_id)):
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
            self.authorization = authorization
            rows = {}
            for module in MODULE_TITLES:
                if self.isInterruptionRequested():
                    return
                if not authorization.allows_module(module):
                    rows[module] = ("denied", None)
                    continue
                try:
                    rows[module] = ("ready", self.delivery.check(module))
                except LicenseUnavailableError:
                    rows[module] = ("error", None)
                except LicenseError:
                    raise
                except Exception:
                    rows[module] = ("error", None)
            self.result = rows
        except LicenseUnavailableError:
            self.failed = True
        except LicenseError:
            self.failed = True
            self.denied = True
        except Exception:
            # Neither provider details, filesystem paths nor tokens enter UI text.
            self.failed = True


class ModuleUpdatesDialog(QDialog):
    news_changed = pyqtSignal(str)
    state_changed = pyqtSignal()
    def __init__(self, delivery, *, busy_module=lambda _module: False, authorization_provider=lambda: None, parent=None):
        super().__init__(parent)
        self.delivery = delivery
        self.busy_module = busy_module
        self.authorization_provider = authorization_provider
        self.worker = None
        self.releases = {}
        self.checked = {}
        self.checked_authorization = None
        self.denied_authorization = None
        self._pending_download = None
        self._shutting_down = False
        # One-at-a-time "update all" queue built by update_all(); only
        # installed modules with a verified offer are ever enqueued.
        self._queue: list[str] = []
        self._queue_total = 0
        self._queue_position = 0
        self._queue_updated = 0
        self._queue_failed: str | None = None
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
        self.update_all_button = V3Button("Обновить все модули", ButtonVariant.PRIMARY)
        self.update_all_button.clicked.connect(self.update_all)
        heading.addWidget(self.update_all_button)
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
        self.cancel_button = V3Button("Отменить скачивание", ButtonVariant.SECONDARY)
        self.cancel_button.clicked.connect(self.cancel_transfer)
        self.cancel_button.hide()
        footer.addWidget(self.cancel_button)
        self.close_button = V3Button("Закрыть", ButtonVariant.SECONDARY)
        self.close_button.clicked.connect(self.reject)
        footer.addWidget(self.close_button)
        layout.addLayout(footer)
        self._refresh_installed()
        if not delivery.store.trusted_keys:
            self.check_button.setEnabled(False)
            self.update_all_button.setEnabled(False)
            self.status.setText("Обновления модулей пока недоступны в этой версии Studio.")
        QApplication.instance().aboutToQuit.connect(self._shutdown)

    @property
    def busy(self):
        return self.worker is not None

    def _refresh_installed(self):
        for module, (installed, _available, _button) in self.rows.items():
            try:
                state = self.delivery.store.state(module)
                installed.setText(state["active"] if state["enabled"] and state["active"] else "Не установлен")
            except Exception:
                installed.setText("Ошибка версии")

    def _start(self, release=None):
        if self.busy:
            return
        self.worker = ModuleUpdateWorker(self.delivery, release, self, authorization=self.authorization_provider())
        self.check_button.setEnabled(False)
        self.update_all_button.setEnabled(False)
        self.close_button.setEnabled(False)
        self.cancel_button.setVisible(release is not None)
        self.cancel_button.setEnabled(True)
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

    def request_module(self, module):
        if module not in self.rows or self.busy:
            return
        self._pending_download = module
        self.check()

    def invalidate_access(self):
        self.checked.clear()
        self.releases.clear()
        self.checked_authorization = None
        self.denied_authorization = None
        self._pending_download = None
        for _installed, available, button in self.rows.values():
            available.setText("Проверьте доступ")
            button.setEnabled(False)

    def cancel_transfer(self):
        self._pending_download = None
        if self.worker is not None:
            self.worker.cancel()
            self.cancel_button.setEnabled(False)
            self.status.setText("Отменяем скачивание. Установленные версии сохранятся.")

    def download(self, module):
        if self.busy or module not in self.releases:
            return
        if self.busy_module(module):
            self.status.setText("Проект открыт. Завершите работу и перезапустите Studio перед обновлением модуля.")
            return
        self.status.setText(f"{MODULE_TITLES[module]}: подготовка загрузки…")
        self.rows[module][2].setText("Скачивание")
        self._start(self.releases[module])

    def _module_installed(self, module):
        try:
            state = self.delivery.store.state(module)
            return bool(state["enabled"] and state["active"])
        except Exception:
            return False

    def update_all(self):
        """Update installed modules with a verified offer, strictly one at a
        time. New or uninstalled modules are never auto-added; a failed
        module keeps its previous working version and stops the queue with
        an honest partial summary."""
        if self.busy:
            return
        queue = [module for module in self.rows
                 if module in self.releases and self._module_installed(module)]
        if not queue:
            self.status.setText("Нет доступных обновлений для установленных модулей. "
                                "Сначала нажмите «Проверить обновления».")
            return
        self._queue = list(queue)
        self._queue_total = len(self._queue)
        self._queue_position = 0
        self._queue_updated = 0
        self._queue_failed = None
        self._advance_queue()

    def _advance_queue(self):
        while self._queue:
            module = self._queue[0]
            if module not in self.releases:
                self._queue.pop(0)
                continue
            if self.busy_module(module):
                self._queue_failed = module
                self._queue = []
                self._finish_queue()
                return
            self._queue_position += 1
            self.status.setText(
                f"Модуль {self._queue_position} из {self._queue_total} — "
                f"{MODULE_TITLES[module]}: подготовка загрузки…")
            self.rows[module][2].setText("Скачивание")
            self._start(self.releases[module])
            return
        self._finish_queue()

    def _finish_queue(self):
        total, updated, failed = self._queue_total, self._queue_updated, self._queue_failed
        self._queue = []
        self._queue_total = 0
        self._queue_position = 0
        self._queue_updated = 0
        self._queue_failed = None
        if failed is None:
            self.status.setText(f"Готово: обновлены все {total} модулей.")
        else:
            self.status.setText(
                f"Обновлено {updated} из {total}. Остановка на «{MODULE_TITLES[failed]}»: "
                "обновление не установлено, прежняя рабочая версия сохранена.")

    def _stop_queue(self):
        self._queue = []
        self._queue_total = 0
        self._queue_position = 0
        self._queue_updated = 0
        self._queue_failed = None

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
            if worker.cancelled:
                self._pending_download = None
                waiting = bool(self._queue)
                if waiting:
                    self._stop_queue()
                self.status.setText("Скачивание отменено. Установленные версии сохранены."
                                    + (" Обновление остальных модулей остановлено." if waiting else ""))
            elif worker.failed:
                self.checked_authorization = None
                self.denied_authorization = worker.initial_authorization if worker.denied else None
                if worker.denied:
                    self.releases.clear()
                self.news_changed.emit("Новости Studio: не удалось проверить обновления")
                self._pending_download = None
                if worker.release is None:
                    self.checked = {}
                    for _installed, available, _button in self.rows.values():
                        available.setText("Ошибка проверки")
                self.status.setText("Не удалось проверить или скачать обновление. Текущая версия сохранена.")
                if self._queue:
                    module = worker.release.module_id if worker.release is not None else self._queue[0]
                    if module in self._queue:
                        self._queue.remove(module)
                    self._queue_failed = module
                    self._finish_queue()
            elif worker.release is None:
                self.denied_authorization = None
                self.checked = dict(worker.result or {})
                self.checked_authorization = worker.authorization
                news = [f"{MODULE_TITLES[module]}: доступно обновление" if isinstance(release, WorkflowUpdate)
                        else f"{MODULE_TITLES[module]} {release.version}: {release.notes}"[:500]
                        for module, (state, release) in (worker.result or {}).items()
                        if state == "ready" and release is not None]
                self.news_changed.emit("Новости Studio\n" + "\n".join(news[:3]) if news else
                    "Новости Studio: обновления не найдены" if all(state == "ready" for state, _ in (worker.result or {}).values())
                    else "Новости Studio: не все модули удалось проверить")
                for module, (state, release) in (worker.result or {}).items():
                    installed, available, button = self.rows[module]
                    available.setText({"denied": "Нет доступа", "error": "Ошибка проверки"}.get(
                        state, ("Доступно обновление" if isinstance(release, WorkflowUpdate) and release.workflow is None
                                else release.version) if release else "Нет обновлений"))
                    button.setText("Нет обновлений" if state == "ready" else "Недоступно")
                    if release is not None:
                        self.releases[module] = release
                self.status.setText("Не все модули удалось проверить. Повторите проверку." if any(
                    state == "error" for state, _release in (worker.result or {}).values()) else "Проверено только что")
            else:
                module = worker.release.module_id
                if self.busy_module(module):
                    self.status.setText("Пакет проверен. Завершите работу и перезапустите Studio перед обновлением модуля.")
                    if self._queue:
                        if module in self._queue:
                            self._queue.remove(module)
                        self._queue_failed = module
                        self._finish_queue()
                else:
                    if isinstance(worker.release, WorkflowUpdate):
                        self.delivery.activate_update(worker.release)
                        # The shared update may satisfy offers in other rows too.
                        # Require a fresh check rather than presenting stale actions.
                        self.releases.clear()
                        for name, (_installed, available, _button) in self.rows.items():
                            if name != module:
                                available.setText("Проверьте обновления")
                        if self._queue:
                            self._stop_queue()
                    else:
                        self.delivery.activate(module, worker.release.version)
                        if self._queue and self._queue[0] == module:
                            self._queue.remove(module)
                            self._queue_updated += 1
                    self.releases.pop(module, None)
                    self.rows[module][2].setText("Установлено")
                    self.status.setText(f"{MODULE_TITLES[module]}: обновление установлено.")
        except Exception:
            self.status.setText("Не удалось активировать обновление. Текущая версия сохранена.")
        finally:
            self.worker = None
            worker.deleteLater()
            self.progress.hide()
            self.cancel_button.hide()
            self.close_button.setEnabled(True)
            self.check_button.setEnabled(bool(self.delivery.store.trusted_keys))
            self.update_all_button.setEnabled(bool(self.delivery.store.trusted_keys))
            self._refresh_installed()
            for module, (_installed, _available, button) in self.rows.items():
                button.setEnabled(module in self.releases and not self._queue)
                from studio_catalog_ui import style_module_action
                style_module_action(button, module in self.releases and not self._queue and button.isEnabled())
                if module in self.releases:
                    installed = self.delivery.store.state(module)
                    button.setText("Обновить" if installed["enabled"] and installed["active"] else "Скачать")
            self.state_changed.emit()
            pending, self._pending_download = self._pending_download, None
            if pending in self.releases and not self._queue:
                QTimer.singleShot(0, lambda: self.download(pending))
            elif self._queue:
                QTimer.singleShot(0, self._advance_queue)
            elif self._queue_total:
                QTimer.singleShot(0, self._finish_queue)


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
            self.worker.cancel()
            self.worker.wait()
