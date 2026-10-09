from types import SimpleNamespace
from unittest.mock import Mock

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication
from PyQt6.QtTest import QTest

from studio_news_ui import StudioNewsPanel, StudioNewsController


def test_plain_text_empty_and_cached_offline_news():
    app = QApplication.instance() or QApplication([])
    panel = StudioNewsPanel()
    assert panel.isHidden()
    item = dict(id='a'*32, title='<img src=x>', body='<b>Не HTML</b>', published_at='2026-09-23T12:00:00+00:00')
    panel.set_news([item], offline=True)
    assert panel.title.textFormat() == Qt.TextFormat.PlainText
    assert panel.body.textFormat() == Qt.TextFormat.PlainText
    assert panel.body.text() == '<b>Не HTML</b>'
    assert not panel.isHidden()
    assert not panel.note.isHidden()
    panel.set_news([])
    assert panel.title.isHidden() and panel.date.isHidden() and panel.note.isHidden()
    assert panel.isHidden()
    assert panel.body.text() == 'Новых объявлений пока нет.'
    panel.close()


def test_failed_refresh_keeps_cached_text_and_does_not_block_ui():
    app = QApplication.instance() or QApplication([])
    panel = StudioNewsPanel()
    item = dict(id='b'*32, title='Saved', body='Content', published_at='2026-09-23T12:00:00+00:00')
    client = SimpleNamespace(cached=lambda: [item], fetch=Mock(side_effect=OSError('private transport detail')))
    controller = StudioNewsController(client, panel, panel)
    try:
        for _ in range(200):
            app.processEvents()
            QTest.qWait(5)
            if client.fetch.called and controller.worker is None:
                break
        assert client.fetch.call_count == 1
        assert panel.body.text() == 'Content'
        assert not panel.note.isHidden()
        assert 'private' not in panel.note.text()
    finally:
        controller.shutdown()
        app.processEvents()
        panel.close()


def test_empty_news_never_reserves_home_space_and_returns_when_published():
    from v3_mode_selection import ModeSelectionScreen
    app = QApplication.instance() or QApplication([])
    screen = ModeSelectionScreen()
    screen.resize(1120, 780)
    screen.show()
    app.processEvents()
    panel = screen.news_panel
    assert panel.isHidden()
    empty_y = screen.catalog_scroll.y()
    item = dict(id='c'*32, title='Новое объявление', body='Текст новости',
                published_at='2026-10-08T12:00:00+00:00')
    try:
        for items, offline in [(None, False), ([], False), (None, True), ([], True)]:
            panel.set_news(items, offline=offline)
            app.processEvents()
            assert panel.isHidden()
            assert screen.catalog_scroll.y() == empty_y
        for offline in (False, True):
            panel.set_news([item], offline=offline)
            app.processEvents()
            assert panel.isVisible()
            assert panel.body.text() == item['body']
            assert screen.catalog_scroll.y() > empty_y
        panel.set_news([])
        app.processEvents()
        assert panel.isHidden()
        assert screen.catalog_scroll.y() == empty_y
    finally:
        screen.close()
        screen.deleteLater()
