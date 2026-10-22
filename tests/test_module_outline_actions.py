from dataclasses import replace

import pytest
from PyQt6.QtWidgets import QApplication

from studio_catalog import ModuleAvailability
from studio_catalog_ui import BUILTIN_CATALOG, StudioCatalogCard
from v3_components import ButtonVariant
from v3_mode_selection import ModeSelectionScreen


@pytest.fixture(scope='module')
def app():
    return QApplication.instance() or QApplication([])


def pump(app):
    for _ in range(5):app.processEvents()


def test_one_update_button_emits_update_once_and_returns_to_dark_open(app):
    availability=ModuleAvailability(installed=True,entitled=True,open_supported=True,
                                    download_supported=True,update_available=True)
    card=StudioCatalogCard(BUILTIN_CATALOG[2],availability)
    intents=[];card.action_requested.connect(lambda *args:intents.append(args))
    assert card.start_button.text()=='Обновить' and card.start_button.menu() is None
    assert card.start_button.property('moduleActionRequired') is True
    assert intents==[]
    card.start_button.click()
    assert intents==[('processing','update')]
    card.set_availability(replace(availability,update_available=False))
    assert card.start_button.text()=='Открыть'
    assert card.start_button.variant is ButtonVariant.SECONDARY
    assert card.start_button.property('moduleActionRequired') is False
    card.start_button.click()
    assert intents[-1]==('processing','open')
    card.close()


def test_offline_or_denied_update_hint_does_not_become_download(app):
    availability=ModuleAvailability(installed=True,entitled=True,open_supported=True,update_available=True)
    card=StudioCatalogCard(BUILTIN_CATALOG[2],availability);intents=[]
    card.action_requested.connect(lambda *args:intents.append(args));card.start_button.click()
    assert intents==[('processing','open')]
    assert not card.start_button.property('moduleActionRequired')
    card.set_availability(replace(availability,entitled=False,download_supported=True))
    card.start_button.click();assert len(intents)==1
    assert not card.start_button.isEnabled()
    card.close()


def test_header_indicator_tracks_actionable_updates_only(app):
    screen=ModeSelectionScreen()
    current=ModuleAvailability(installed=True,entitled=True,open_supported=True,download_supported=True)
    screen.set_module_catalog(BUILTIN_CATALOG,{e.module_id:current for e in BUILTIN_CATALOG})
    assert not screen.module_updates_button.property('moduleActionRequired')
    screen.module_cards['processing'].set_availability(replace(current,update_available=True))
    screen.refresh_module_update_indicator()
    assert screen.module_updates_button.property('moduleActionRequired')
    screen.module_cards['processing'].set_availability(current)
    screen.refresh_module_update_indicator()
    assert not screen.module_updates_button.property('moduleActionRequired')
    screen.close()


def test_card_sizes_stay_constant_and_columns_follow_window(app):
    screen=ModeSelectionScreen();screen.resize(1120,780);screen.show();pump(app)
    cards=list(screen.module_cards.values())
    initial=[(c.width(),c.height(),c.illustration.width(),c.illustration.height()) for c in cards]
    assert {c.width() for c in cards}=={349}
    assert screen.cards_layout.getItemPosition(3)[:2]==(1,0)
    screen.resize(1920,1080);pump(app)
    assert [(c.width(),c.height(),c.illustration.width(),c.illustration.height()) for c in cards]==initial
    assert screen.cards_layout.getItemPosition(4)[:2]==(0,4)
    left=cards[0].x();right=screen.catalog_scroll.viewport().width()-cards[4].geometry().right()-1
    assert abs(left-right)<=1
    screen.resize(980,700);pump(app)
    assert screen.cards_layout.getItemPosition(4)[:2]==(2,0)
    scroll=screen.catalog_scroll;scroll.verticalScrollBar().setValue(scroll.verticalScrollBar().maximum());pump(app)
    bottom=cards[-1].start_button.mapTo(scroll.viewport(),cards[-1].start_button.rect().bottomRight())
    assert bottom.y()<=scroll.viewport().height()
    screen.resize(1120,780);pump(app)
    assert {c.width() for c in cards}=={349}
    assert screen.cards_layout.getItemPosition(3)[:2]==(1,0)
    assert not screen.catalog_scroll.verticalScrollBar().isVisible()
    screen.close()
