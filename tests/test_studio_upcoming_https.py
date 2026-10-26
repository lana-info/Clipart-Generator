"""Real admin HTTP -> signed licensed feed -> Qt catalogue; fixture data only."""
import base64
from datetime import datetime, timedelta, timezone
import io
from unittest.mock import Mock

import pytest
from PIL import Image
from PyQt6.QtTest import QTest

from tests.test_studio_module_delivery_integration import delivery, app
from studio_catalog import ModuleAvailability
from studio_module_release import AdminDraftUploader
from update_client import UpdateError
from v3_mode_selection import V3ApplicationView

pytestmark = pytest.mark.network


def test_real_admin_publish_signed_refresh_tamper_offline_and_withdraw(delivery, app, tmp_path, monkeypatch):
    from license_service.admin import current_totp
    bridge, _, gate, service, record = delivery
    boot=bridge.test_admin.bootstrap('upcoming isolated fixture password')
    secret=base64.b32decode(boot.totp_secret_base32+'='*(-len(boot.totp_secret_base32)%8))
    uploader=AdminDraftUploader(bridge.test_service_url)
    uploader.login('admin','upcoming isolated fixture password',current_totp(secret))
    buffer=io.BytesIO();Image.new('RGBA',(4,3),(30,190,170,255)).save(buffer,format='PNG')
    row=uploader._post('/admin/upcoming',dict(title='Паттерны',description='Бесшовные узоры',sort_order=2,preview_png=base64.b64encode(buffer.getvalue()).decode()))
    assert bridge.upcoming.fetch()==[]
    pub=uploader._post('/admin/upcoming/status',dict(id=row['id'],revision=row['revision'],status='published'))
    service.update_license(record.license_id,updates_until=datetime.now(timezone.utc)-timedelta(days=1))
    # Promotional metadata remains accessible without an update subscription.
    items=bridge.upcoming.fetch();assert [r['title'] for r in items]==['Паттерны']
    workers=Mock(side_effect=AssertionError('Promotional cards cannot run paid work'))
    view=V3ApplicationView(draft_path=tmp_path/'draft.json',license_gate=gate,module_delivery=bridge,worker_factory=workers)
    try:
        controller=view._upcoming_controller;controller.timer.stop()
        for _ in range(300):
            app.processEvents();QTest.qWait(5)
            if controller.worker is None and 'upcoming-'+row['id'] in view.mode_selection.module_cards:break
        else:raise AssertionError('Signed card was not shown in real Qt catalogue')
        card=view.mode_selection.module_cards['upcoming-'+row['id']]
        assert card.start_button.text()=='Скоро выйдет' and not card.start_button.isEnabled()
        card.start_button.click();card.selected.emit(card.entry.module_id);workers.assert_not_called()
        builtin=view.mode_selection.module_cards['clipart'];availability=builtin.availability
        trusted_request=bridge.updates.license_client.authenticated_request
        def tampered(*args,**kwargs):
            envelope,device,nonce=trusted_request(*args,**kwargs)
            envelope['payload']['cards'][0]['title']='Tampered unsigned title'
            return envelope,device,nonce
        monkeypatch.setattr(bridge.updates.license_client,'authenticated_request',tampered)
        with pytest.raises(UpdateError):bridge.upcoming.fetch()
        assert bridge.upcoming.cached()==items
        controller.refresh()
        for _ in range(300):
            app.processEvents();QTest.qWait(5)
            if controller.worker is None:break
        assert view.mode_selection.module_cards['upcoming-'+row['id']].entry.title=='Паттерны'
        assert view.mode_selection.module_cards['clipart'] is builtin and builtin.availability==availability
        monkeypatch.setattr(bridge.updates.license_client,'authenticated_request',trusted_request)
        uploader._post('/admin/upcoming/status',dict(id=row['id'],revision=pub['revision'],status='withdrawn'))
        controller.refresh()
        for _ in range(300):
            app.processEvents();QTest.qWait(5)
            if controller.worker is None:break
        assert 'upcoming-'+row['id'] not in view.mode_selection.module_cards
        assert bridge.upcoming.cached()==[] and view.mode_selection.module_cards['clipart'] is builtin
        assert service.upcoming.published()==[]
    finally:
        view._upcoming_controller.shutdown();view._news_controller.shutdown();view.close();app.processEvents();uploader.close()


def test_real_admin_module_order_reaches_signed_feed_and_qt_catalogue(delivery, app, tmp_path):
    from license_service.admin import current_totp
    bridge, _, gate, service, record = delivery
    boot=bridge.test_admin.bootstrap('order isolated fixture password')
    secret=base64.b32decode(boot.totp_secret_base32+'='*(-len(boot.totp_secret_base32)%8))
    uploader=AdminDraftUploader(bridge.test_service_url)
    uploader.login('admin','order isolated fixture password',current_totp(secret))
    view=V3ApplicationView(draft_path=tmp_path/'draft.json',license_gate=gate,module_delivery=bridge)
    try:
        controller=view._upcoming_controller;controller.timer.stop()
        names=list(view.mode_selection.module_cards)
        wanted=[names[-1],names[0]]
        saved=uploader._post('/admin/module-order',dict(module_ids=wanted,revision=0))
        assert saved['module_ids']==wanted
        bridge.upcoming.fetch();assert bridge.upcoming.module_order==wanted
        controller.refresh()
        for _ in range(300):
            app.processEvents();QTest.qWait(5)
            if controller.worker is None:break
        screen=view.mode_selection
        position=lambda key:screen.cards_layout.getItemPosition(screen.cards_layout.indexOf(screen.module_cards[key]))[:2]
        assert position(names[-1])<position(names[0])<position(names[1])
        assert list(screen.module_cards)==names
    finally:
        view._upcoming_controller.shutdown();view._news_controller.shutdown();view.close();app.processEvents();uploader.close()
