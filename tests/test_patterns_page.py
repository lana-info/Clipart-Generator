"""The Patterns page runs from the signed package and drives the Core host end to end."""
import os
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from PIL import Image, ImageDraw, ImageFilter
from PyQt6.QtWidgets import QApplication, QMessageBox

from studio_module_packaging import prepare_official_workflow_release
from studio_module_runtime import ModuleRuntimeHost
from studio_modules import ModuleStore
from studio_patterns_host import PatternsHost

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture(scope="module")
def runtime(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("patterns-page-runtime")
    key = Ed25519PrivateKey.generate()  # Ephemeral test signer; no publisher key material.
    public = key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    package = prepare_official_workflow_release(
        source_root=ROOT, module_id="patterns", version="1.0.0", studio_min="3.2.8",
        studio_max_exclusive="3.3.0", platforms=["linux-x64"], key_id="test", private_key=key)
    (tmp / "patterns.zip").write_bytes(package)
    store = ModuleStore(tmp / "modules", studio_version="3.2.8", platform="linux-x64", trusted_keys={"test": public})
    store.install(tmp / "patterns.zip")
    store.activate("patterns", "1.0.0")
    allowed = {"load", "command:kernel", "page:main"}
    host = ModuleRuntimeHost(store, lambda module, action: module == "patterns" and action in allowed)
    host.load_active("patterns")
    yield host
    host.unload("patterns")


@pytest.fixture
def dialogs(monkeypatch):
    shown = []
    for name in ("warning", "information"):
        monkeypatch.setattr(QMessageBox, name, staticmethod(lambda parent, title, text, *a, **k: shown.append(text)))
    return shown


def pump(app, predicate, seconds=60):
    deadline = time.monotonic() + seconds
    while not predicate() and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.005)
    app.processEvents()
    assert predicate()


def make_pngs(folder, count=3):
    paths = []
    for index in range(count):
        image = Image.new("RGBA", (200, 200), (0, 0, 0, 0))
        ImageDraw.Draw(image).ellipse((20, 20, 180, 180), fill=(60 + index * 60, 100, 160, 255))
        path = folder / f"motif{index}.png"
        image.save(path)
        paths.append(str(path))
    return paths


def open_page(runtime, tmp_path, name="root"):
    kernel = runtime.invoke_command("patterns", "kernel")
    host = PatternsHost(tmp_path / name, authorize=lambda: True, runtime=runtime, kernel=kernel)
    handle = runtime.create_page("patterns", "main", host)
    return handle, handle.value, host


def close_page(app, handle, page, host):
    page._busy = False
    host.close()
    page.deleteLater()
    app.processEvents()
    handle.close()


def test_page_runs_from_the_signed_package(runtime, app, tmp_path):
    handle, page, host = open_page(runtime, tmp_path)
    assert page.__class__.__module__.startswith("_studio_module_patterns_")
    assert [label.text() for label in page.step_labels][0].startswith("● 1.")
    assert not page.next_button.isEnabled() and not page.back_button.isEnabled()
    close_page(app, handle, page, host)


def test_full_flow_from_pngs_to_exported_files(runtime, app, tmp_path, dialogs):
    handle, page, host = open_page(runtime, tmp_path)
    page._add_assets(make_pngs(tmp_path))
    assert len(page._assets) == 3 and page.next_button.isEnabled()
    page._add_assets(make_pngs(tmp_path))  # the same files again are not duplicated
    assert len(page._assets) == 3
    page._go_next()
    page._settings["inches"] = 2.0  # keep the sheet small and the test fast
    page._invalidate(layout=True)
    page._go_next()
    pump(app, lambda: page._current is not None)
    assert page._current["seam"]["status"] == "ready" and page._current["image"].size == (600, 600)
    assert page.primary_action.text() == "Добавить лист в набор" and page.next_button.isEnabled()
    page._settings["sheet_count"] = 3
    page._go_next()
    pump(app, lambda: len(page._sheets) == 3 and not page._busy)
    assert all(sheet["included"] for sheet in page._sheets)
    seeds = {sheet["seed"] for sheet in page._sheets}
    assert len(seeds) == 3  # "different seeds" by default
    page._select_sheet(1)
    before = page._sheets[1]["image"].tobytes()
    page._reroll_selected()
    pump(app, lambda: not page._busy)
    assert page._sheets[1]["image"].tobytes() != before
    page._go_next()
    assert page._step == 4 and not page.next_button.isEnabled()  # no folder yet
    folder = tmp_path / "out"
    folder.mkdir()
    page._export_folder = str(folder)
    page._settings["set_name"] = "Весенний сад"
    page._refresh()
    assert page.next_button.isEnabled() and page.next_button.text() == "Экспортировать"
    page._go_next()
    pump(app, lambda: not page._busy and dialogs)
    names = sorted(p.name for p in folder.iterdir())
    assert names == ["Весенний сад 01.png", "Весенний сад 02.png", "Весенний сад 03.png"]
    with Image.open(folder / names[0]) as saved:
        assert saved.size == (600, 600)
    # A second export would overwrite: Core refuses and the page explains.
    dialogs.clear()
    page._go_next()
    assert any("уже существуют" in text for text in dialogs)
    assert sorted(p.name for p in folder.iterdir()) == names
    close_page(app, handle, page, host)


def test_projects_are_saved_and_restored(runtime, app, tmp_path, dialogs):
    handle, page, host = open_page(runtime, tmp_path, "persist")
    page._add_assets(make_pngs(tmp_path))
    page._settings.update(count=9, seed=77, set_name="Сохранённый")
    page._go_next()
    assert page._project_id is not None
    close_page(app, handle, page, host)
    handle, again, host = open_page(runtime, tmp_path, "persist")
    assert len(again._assets) == 3 and again._settings["seed"] == 77 and again._settings["count"] == 9
    assert again._assets[0]["width"] == 200  # sizes come back from the stored files
    assert again.title.text() == "Patterns · Сохранённый"
    close_page(app, handle, again, host)


def test_tile_mode_hides_unsupported_choices_and_fails_visibly(runtime, app, tmp_path, dialogs):
    handle, page, host = open_page(runtime, tmp_path)
    page._set_mode("tile")
    assert not page.next_button.isEnabled() and page.pick_tile.isVisibleTo(page) and not page.add_files.isVisibleTo(page)
    cut = Image.new("RGB", (160, 120))
    ramp = ImageDraw.Draw(cut)
    for x in range(160):
        ramp.line((x, 0, x, 119), fill=(x * 255 // 159, 40, 200 - x))
    path = tmp_path / "tile.png"
    cut.save(path)
    page._tile = {**host.import_png(path), "name": "tile.png"}
    page._refresh()
    page._go_next()
    assert page._step == 1 and page.tile_controls.isVisibleTo(page) and not page.png_controls.isVisibleTo(page)
    page._go_next()
    pump(app, lambda: page._current is not None)
    assert page._current["image"].size == (160, 120)
    # Pretend the engine judged this attempt a failure: the actions change accordingly.
    page._current = {"image": page._current["image"], "seam": {**page._current["seam"], "status": "fail", "score": 9.0}}
    page._refresh()
    assert page.primary_action.text() == "Сделать бесшовной" and page.secondary_action.text().startswith("Оставить")
    assert not page.next_button.isEnabled()
    page.secondary_action.click()  # keep as is: the sheet joins the set as Review and stays exportable
    assert page._step == 3 and len(page._sheets) == 1
    assert page._sheets[0]['status'] == 'review' and page._sheets[0]['included']
    close_page(app, handle, page, host)


def test_bad_files_are_reported_and_closing_while_busy_asks(runtime, app, tmp_path, dialogs, monkeypatch):
    handle, page, host = open_page(runtime, tmp_path)
    broken = tmp_path / "broken.png"
    broken.write_bytes(b"nope")
    page._add_assets([str(broken)])
    assert page._assets == [] and any("broken.png" in text for text in dialogs)
    assert page.confirm_close() is True
    page._busy = True
    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.StandardButton.No))
    assert page.confirm_close() is False
    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes))
    assert page.confirm_close() is True
    close_page(app, handle, page, host)


def test_preview_buttons_add_the_sheet_or_reroll_it(runtime, app, tmp_path, dialogs):
    handle, page, host = open_page(runtime, tmp_path)
    page._add_assets(make_pngs(tmp_path))
    page._settings["inches"] = 2.0
    page._go_next()
    page._go_next()
    pump(app, lambda: page._current is not None)
    seed = page._settings["seed"]
    page.secondary_action.click()  # a new seed gives a new render
    pump(app, lambda: page._current is not None and not page._busy)
    assert page._settings["seed"] == seed + 1
    page.primary_action.click()
    assert page._step == 3
    pump(app, lambda: len(page._sheets) == page._settings['sheet_count'] and not page._busy)
    close_page(app, handle, page, host)


def test_main_window_opens_and_closes_patterns_from_the_signed_package(app, tmp_path, runtime, dialogs):
    from types import SimpleNamespace
    from unittest.mock import patch
    from v3_mode_selection import V3ApplicationView
    view = V3ApplicationView(draft_path=tmp_path / "draft.json")
    view.resize(1120, 780)
    view.show()
    view._module_delivery = SimpleNamespace(host=runtime)
    view._license_gate = object()
    try:
        assert "patterns" in view.mode_selection.module_cards
        with patch("v3_mode_selection.authorize_module_run"), patch.object(view, "_patterns_allowed", return_value=True):
            view._open_patterns()
        assert dialogs == []
        page = view._patterns_page_handle.value
        app.processEvents()
        assert page.__class__.__module__.startswith("_studio_module_patterns_")
        assert view.stack.currentWidget() is page
        with patch("v3_mode_selection.authorize_module_run"), patch.object(view, "_patterns_allowed", return_value=True):
            view._open_patterns()  # a second open reuses the live page
        assert view._patterns_page_handle.value is page
        with patch.object(view, "show_new_project") as home:  # the synthetic license gate has no status text
            view._close_patterns()
        home.assert_called_once()
        assert view._patterns_page_handle is None
    finally:
        if view._patterns_page_handle is not None:
            handle = view._patterns_page_handle
            handle.value.host.close()
            view.stack.removeWidget(handle.value)
            handle.close()
            handle.value.deleteLater()
            view._patterns_page_handle = None
        view._module_delivery = None
        view._license_gate = None
        view.close()
        view.deleteLater()
        app.processEvents()


def _patterns_view(tmp_path, gate):
    from v3_mode_selection import V3ApplicationView
    return V3ApplicationView(draft_path=tmp_path / "draft.json", license_gate=gate, module_delivery=None)


def _patterns_auth(now, minutes):
    from datetime import timedelta
    from license_client import LicenseAuthorization, ModuleEntitlement
    return LicenseAuthorization("fixture", "clipart-generator", "device", now - timedelta(minutes=minutes + 1),
        now - timedelta(minutes=minutes) + timedelta(minutes=5),
        module_entitlements=(ModuleEntitlement("patterns", now - timedelta(days=1), now + timedelta(days=1)),))


def test_patterns_access_is_not_rechecked_while_open(app, tmp_path):
    from datetime import datetime, timezone
    from types import SimpleNamespace
    from unittest.mock import Mock
    now = datetime.now(timezone.utc)
    gate = SimpleNamespace(current_authorization=_patterns_auth(now, 10), authorize_run=Mock(),
                           status_text="Лицензия активна", verification_text="Проверено")
    view = _patterns_view(tmp_path, gate)
    try:
        assert view._patterns_allowed() is True  # authorization expired 5+ minutes ago
        gate.authorize_run.assert_not_called()
    finally:
        view.deleteLater()


# ---- Owner remarks П1, П4, П5, П6, П8 (approved mockups docs/ui/3.2/patterns-owner-remarks/, 2026-10-23)

def test_no_plaque_and_only_add_png_button(runtime, app, tmp_path):
    from PyQt6.QtWidgets import QPushButton
    handle, page, host = open_page(runtime, tmp_path)
    page.show(); app.processEvents()
    visible = {b.text() for b in page.findChildren(QPushButton) if b.isVisible()}
    assert not visible & {"Главная Studio", "Настройки API", "Диагностика"}   # П1: the Studio header has them
    assert page.add_files.isVisible() and not page.add_folder.isVisible()       # owner edit: no «Добавить папку»
    close_page(app, handle, page, host)


def test_ready_tile_texts_name_the_file_and_need_no_transparency(runtime, app, tmp_path):
    handle, page, host = open_page(runtime, tmp_path)
    page.show()
    page._set_mode("tile")
    assert page.pick_tile.text() == "Выбрать файл"
    assert "Выберите картинку" in page.source_empty.text()
    tile = tmp_path / "tile.png"
    Image.new("RGB", (600, 400), (120, 80, 40)).save(tile)
    page._tile = {**host.import_png(str(tile)), "name": "tile.png"}
    page._refresh(); app.processEvents()
    texts = [page.checks.itemAt(i).widget().text() for i in range(page.checks.count())]
    assert texts[0] == "Прозрачный фон для готовой плитки не нужен."
    assert "Выбран файл tile.png · 600 × 400 px" in texts[1]
    assert not any("прозрачным фоном" in t for t in texts)
    assert page.pick_tile.text() == "Выбрать другой файл"
    close_page(app, handle, page, host)


def test_not_enough_room_message_is_russian_and_follows_the_slider(runtime, app, tmp_path):
    handle, page, host = open_page(runtime, tmp_path)
    page._add_assets(make_pngs(tmp_path))
    page._settings.update(inches=2.0, count=60, gap=300)
    page._go_next()
    page._elements = page._relayout()
    page._refresh()
    note = page.layout_note.text()
    assert note.startswith("Поставлено ") and "из 60 элементов" in note and "при зазоре 300 px" in note
    assert "placed" not in note
    page._settings["count"] = 6
    page._invalidate(layout=True)
    page._refresh()
    assert "из 60" not in page.layout_note.text()   # no stale message after the slider moved
    close_page(app, handle, page, host)


def test_background_colour_can_be_picked(runtime, app, tmp_path, monkeypatch):
    from PyQt6.QtGui import QColor
    from PyQt6.QtWidgets import QColorDialog
    handle, page, host = open_page(runtime, tmp_path)
    page._settings["transparent"] = True
    monkeypatch.setattr(QColorDialog, "getColor", staticmethod(lambda *a, **k: QColor(10, 120, 200)))
    page._pick_background()
    assert page._settings["background"] == [10, 120, 200, 255] and not page._settings["transparent"]
    assert page.background_name.text().startswith("Свой цвет #0A78C8")
    close_page(app, handle, page, host)


def test_too_large_png_offers_a_smaller_copy(runtime, app, tmp_path, dialogs):
    from studio_patterns_storage import PatternsImageTooLarge
    big = tmp_path / "rough_03_upscaled-after.png"
    Image.new("RGBA", (9000, 600), (200, 100, 100, 255)).save(big)
    handle, page, host = open_page(runtime, tmp_path)
    with pytest.raises(PatternsImageTooLarge) as caught:
        host.import_png(str(big))
    assert (caught.value.width, caught.value.height) == (9000, 600) and "9000 × 600 px" in str(caught.value)
    offered = []
    page._offer_smaller_copy = lambda path, error: offered.append((Path(path).name, error.width)) or True
    page._add_assets([str(big)])
    assert offered == [("rough_03_upscaled-after.png", 9000)]
    assert len(page._assets) == 1 and page._assets[0]["width"] == 4000 and dialogs == []
    assert Image.open(big).size == (9000, 600)          # the source file is not changed
    page._offer_smaller_copy = lambda path, error: False  # «Пропустить файл»
    page._assets.clear()
    page._add_assets([str(big)])
    assert page._assets == [] and dialogs == []
    close_page(app, handle, page, host)
