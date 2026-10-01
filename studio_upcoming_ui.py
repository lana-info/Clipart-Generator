"""Nonblocking promotional catalogue refresh; content never authorizes actions."""
from PyQt6.QtCore import QObject, QThread, QTimer
from PyQt6.QtWidgets import QApplication


class _UpcomingWorker(QThread):
    def __init__(self, client, parent):
        super().__init__(parent)
        self.client, self.result, self.failed = client, None, False

    def run(self):
        try:
            self.result = self.client.fetch()
        except Exception:
            self.failed = True


class StudioUpcomingController(QObject):
    def __init__(self, client, screen, parent):
        super().__init__(parent)
        self.client, self.screen = client, screen
        self.worker, self.closed = None, False
        self.screen.set_upcoming_cards(client.cached() or [])
        self.timer = QTimer(self)
        self.timer.setInterval(10 * 60 * 1000)
        self.timer.timeout.connect(self.refresh)
        self.timer.start()
        QTimer.singleShot(0, self.refresh)
        QApplication.instance().aboutToQuit.connect(self.shutdown)

    def refresh(self):
        if self.closed or self.worker is not None:
            return
        self.worker = _UpcomingWorker(self.client, self)
        self.worker.finished.connect(self._finished)
        self.worker.start()

    def _finished(self):
        worker = self.worker
        if worker is None:
            return
        if not self.closed and not worker.failed:
            try:
                self.screen.set_upcoming_cards(worker.result)
            except (ValueError, TypeError):
                pass  # A failed GUI decode must preserve the visible catalogue.
        self.worker = None
        worker.deleteLater()

    def shutdown(self):
        self.closed = True
        self.timer.stop()
        if self.worker is not None:
            self.worker.wait()  # Shared transport has bounded HTTP timeouts.
