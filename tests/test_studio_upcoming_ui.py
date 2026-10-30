import threading
from types import SimpleNamespace
from unittest.mock import Mock

from PyQt6.QtCore import Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication

from studio_catalog import ModuleAvailability
from studio_upcoming_ui import StudioUpcomingController
from v3_mode_selection import ModeSelectionScreen
from tests.test_studio_upcoming import card


def wait_finished(app, controller):
    for _ in range(200):
        app.processEvents()
        QTest.qWait(5)
        if controller.worker is None:
            return
    raise AssertionError('Refresh did not finish')


def test_real_catalog_disabled_plain_text_and_withdrawal_preserve_rights():
    app = QApplication.instance() or QApplication([])
    screen = ModeSelectionScreen()
    screen.resize(1120, 780)
    screen.show()
    builtins = dict(screen.module_cards)
    availability = ModuleAvailability(installed=True, entitled=True, open_supported=True)
    builtins['clipart'].set_availability(availability)
    received = []
    screen.module_action_requested.connect(lambda *args: received.append(args))
    screen.set_upcoming_cards([card(title='<b>Узоры</b>', description='<img src=external>')])
    upcoming = screen.module_cards['upcoming-'+'a'*32]
    assert upcoming.start_button.text() == 'Скоро выйдет'
    assert not upcoming.start_button.isEnabled()
    assert upcoming.title_label.textFormat() == upcoming.description_label.textFormat() == Qt.TextFormat.PlainText
    assert not upcoming.illustration._source_pixmap.isNull()
    upcoming.start_button.click()
    upcoming.selected.emit(upcoming.entry.module_id)
    upcoming._request_action(upcoming.entry.module_id)
    assert received == []
    assert all(screen.module_cards[key] is value for key, value in builtins.items())
    assert screen.module_cards['clipart'].availability == availability
    app.processEvents()
    screen.set_upcoming_cards([])
    assert screen.module_cards == builtins
    assert builtins['clipart'].start_button.isEnabled()
    screen.close()


def test_async_startup_update_offline_withdraw_and_single_inflight():
    app = QApplication.instance() or QApplication([])
    screen = ModeSelectionScreen()
    builtins = dict(screen.module_cards)
    ready = threading.Event()
    cached = [card()]
    client = SimpleNamespace(cached=lambda: cached, fetch=Mock(side_effect=lambda: (ready.wait(2), [card(title='Обновлено')])[1]))
    controller = StudioUpcomingController(client, screen, screen)
    try:
        assert screen.module_cards['upcoming-'+'a'*32].entry.title == 'Узоры'
        controller.refresh()
        worker = controller.worker
        controller.refresh()
        app.processEvents()
        assert controller.worker is worker
        assert controller.timer.interval() == 600000
        ready.set()
        wait_finished(app, controller)
        assert client.fetch.call_count == 1
        assert screen.module_cards['upcoming-'+'a'*32].entry.title == 'Обновлено'
        client.fetch.side_effect = OSError('offline')
        controller.refresh()
        wait_finished(app, controller)
        assert screen.module_cards['upcoming-'+'a'*32].entry.title == 'Обновлено'
        client.fetch.side_effect = None
        client.fetch.return_value = []
        controller.refresh()
        wait_finished(app, controller)
        assert screen.module_cards == builtins
    finally:
        ready.set()
        controller.shutdown()
        controller.refresh()
        assert not controller.timer.isActive()
        app.processEvents()
        screen.close()


def test_maximum_catalog_scroll_and_invalid_refresh_leave_real_cards_intact():
    app = QApplication.instance() or QApplication([])
    screen = ModeSelectionScreen()
    screen.resize(1120, 780)
    screen.show()
    app.processEvents()
    builtins = dict(screen.module_cards)
    screen.set_upcoming_cards([card(id=f'{i:032x}', sort_order=i) for i in range(12)])
    app.processEvents()
    assert len(screen.module_cards) == 18
    scroll = screen.catalog_scroll
    # Qt posts the QScrollArea layout/range update after the new cards are shown.
    for _ in range(50):
        if scroll.verticalScrollBar().maximum() > 0:
            break
        QTest.qWait(5)
    assert scroll.verticalScrollBar().maximum() > 0
    scroll.verticalScrollBar().setValue(scroll.verticalScrollBar().maximum())
    app.processEvents()
    last = list(screen.module_cards.values())[-1].start_button
    assert last.mapTo(scroll.viewport(), last.rect().bottomRight()).y() <= scroll.viewport().height()
    previous = dict(screen.module_cards)
    import pytest
    with pytest.raises(ValueError):
        screen.set_upcoming_cards([card(preview_png='bad')])
    assert screen.module_cards == previous
    screen.set_upcoming_cards([])
    assert screen.module_cards == builtins
    screen.close()


def test_shutdown_inflight_never_applies_result():
    app = QApplication.instance() or QApplication([])
    screen = ModeSelectionScreen()
    client = SimpleNamespace(cached=lambda: [card()], fetch=Mock(return_value=[]))
    controller = StudioUpcomingController(client, screen, screen)
    controller.refresh()
    controller.shutdown()
    app.processEvents()
    assert 'upcoming-'+'a'*32 in screen.module_cards
    assert controller.closed and not controller.timer.isActive()
    screen.close()


def test_deep_malformed_cache_does_not_break_controller_startup(tmp_path):
    from studio_upcoming import StudioUpcomingClient
    app = QApplication.instance() or QApplication([])
    screen = ModeSelectionScreen()
    updates = Mock()
    updates.license_client.product_id = 'clipart-generator'
    updates._request_manifest.side_effect = OSError('offline')
    client = StudioUpcomingClient(updates, tmp_path / 'upcoming.json')
    client.cache_path.write_text('['*20000 + ']'*20000)
    assert client.cached() is None
    builtins = dict(screen.module_cards)
    controller = StudioUpcomingController(client, screen, screen)
    try:
        controller.refresh()
        wait_finished(app, controller)
        assert screen.module_cards == builtins
    finally:
        controller.shutdown()
        screen.close()


def test_promotional_refresh_keeps_wide_grid_and_compact_cards():
    app = QApplication.instance() or QApplication([])
    screen = ModeSelectionScreen()
    screen.resize(1920, 1080)
    screen.show()
    for _ in range(5):
        app.processEvents()
    builtins = dict(screen.module_cards)
    screen.set_upcoming_cards([card(id=f'{i:032x}') for i in range(8)])
    for _ in range(5):
        app.processEvents()
    assert all(c.width() == 349 for c in screen.module_cards.values())
    assert screen.cards_layout.getItemPosition(4)[:2] == (0, 4)
    assert all(screen.module_cards[k] is c for k, c in builtins.items())
    screen.set_upcoming_cards([])
    for _ in range(5):
        app.processEvents()
    assert screen.module_cards == builtins
    assert screen.cards_layout.getItemPosition(4)[:2] == (0, 4)
    screen.close()


def test_server_module_order_arranges_cards_and_keeps_rights():
    _app = QApplication.instance() or QApplication([])
    screen = ModeSelectionScreen()
    screen.resize(1120, 780)
    screen.show()
    names = list(screen.module_cards)
    assert len(names) >= 3

    def visual():
        positions = {}
        for module_id, card_widget in screen.module_cards.items():
            index = screen.cards_layout.indexOf(card_widget)
            row, column, _, _ = screen.cards_layout.getItemPosition(index)
            positions[module_id] = (row, column)
        return [m for m, _ in sorted(positions.items(), key=lambda item: item[1])]
    assert visual() == names
    screen.set_module_order([names[2], 'unknown-module', names[0]])
    assert visual()[:3] == [names[2], names[0], names[1]]
    assert list(screen.module_cards) == names  # only presentation changes
    screen.set_module_order([])
    assert visual() == names
    try:
        screen.set_module_order(['BAD'])
    except ValueError:
        pass
    else:
        raise AssertionError('invalid order accepted')
    assert visual() == names
    screen.close()
