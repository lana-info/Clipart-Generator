"""Plain-text home announcements with nonblocking, bounded refresh."""
from datetime import datetime

from PyQt6.QtCore import QObject, QThread, QTimer, Qt
from PyQt6.QtWidgets import QApplication, QFrame, QLabel, QVBoxLayout, QHBoxLayout


class StudioNewsPanel(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setProperty('v3Card', True)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        row = QHBoxLayout()
        heading = QLabel('Новости Studio')
        heading.setStyleSheet('font-weight:600;')
        row.addWidget(heading)
        row.addStretch()
        self.date = QLabel()
        self.date.setProperty('v3Description', True)
        row.addWidget(self.date)
        layout.addLayout(row)
        self.title = QLabel()
        self.title.setStyleSheet('font-weight:600; color:#25c6b4;')
        self.body = QLabel()
        self.note = QLabel()
        self.note.setProperty('v3Description', True)
        for label in (self.title, self.body, self.note):
            label.setTextFormat(Qt.TextFormat.PlainText)
            label.setWordWrap(True)
            layout.addWidget(label)
        self.set_news(None)

    def set_news(self, items, *, offline=False):
        row = items[0] if items else None
        self.setVisible(row is not None)
        self.title.setVisible(row is not None)
        self.date.setVisible(row is not None)
        self.note.setVisible(offline and row is not None)
        if row:
            self.title.setText(row['title'])
            self.body.setText(row['body'])
            stamp = datetime.fromisoformat(row['published_at'])
            months = ('января', 'февраля', 'марта', 'апреля', 'мая', 'июня', 'июля',
                      'августа', 'сентября', 'октября', 'ноября', 'декабря')
            self.date.setText(f'{stamp.day} {months[stamp.month - 1]}')
            self.note.setText('Сохранённое объявление. Сейчас не удалось обновить новости.')
        else:
            self.body.setText('Сейчас не удалось загрузить новости.' if offline
                              else 'Новых объявлений пока нет.' if items is not None
                              else 'Новости ещё не загружены.')


class _NewsWorker(QThread):
    def __init__(self, client, parent):
        super().__init__(parent)
        self.client, self.result, self.failed = client, None, False

    def run(self):
        try:
            self.result = self.client.fetch()
        except Exception:
            self.failed = True


class StudioNewsController(QObject):
    def __init__(self, client, panel, parent):
        super().__init__(parent)
        self.client, self.panel = client, panel
        self.worker = None
        self.closed = False
        self.panel.set_news(client.cached())
        self.timer = QTimer(self)
        self.timer.setInterval(10 * 60 * 1000)
        self.timer.timeout.connect(self.refresh)
        self.timer.start()
        QTimer.singleShot(0, self.refresh)
        QApplication.instance().aboutToQuit.connect(self.shutdown)

    def refresh(self):
        if self.closed or self.worker is not None:
            return
        self.worker = _NewsWorker(self.client, self)
        self.worker.finished.connect(self._finished)
        self.worker.start()

    def _finished(self):
        worker = self.worker
        if worker is None:
            return
        if not self.closed:
            self.panel.set_news(self.client.cached() if worker.failed else worker.result, offline=worker.failed)
        self.worker = None
        worker.deleteLater()

    def shutdown(self):
        self.closed = True
        self.timer.stop()
        if self.worker is not None:
            # Bounded by the shared transport, but a shutdown must never hang on it:
            # wait briefly, then let the process exit without the window frozen.
            self.worker.wait(2000)
