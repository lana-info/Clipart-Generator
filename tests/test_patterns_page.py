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
from studio_patterns_page import SheetEditor

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
    wait_until_idle(QApplication.instance() or QApplication([]), host)
    try:
        host.unload("patterns")
    except Exception as error:  # report what is still busy instead of a generic refusal
        print("patterns teardown: still busy —",
              f"jobs={getattr(host, '_active_jobs', {}).get('patterns')}",
              f"job_leases={len(getattr(host, '_job_leases', {}).get('patterns') or ())}",
              f"page_leases={len(getattr(host, '_page_leases', {}).get('patterns') or ())}",
              flush=True)
        raise error


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


def wait_until_idle(app, host, module_id="patterns", timeout=20.0):
    """Wait for the module to finish its background work before closing it.

    The module runtime refuses to unload a module with active jobs or live pages. A
    resize of a big PNG (the too-large-copy test) is done by the module itself and can
    still be running when a test closes its page, which made the whole file's teardown
    fail at random (observed in CI 2026-10-29). Waiting removes the race instead of
    hiding it: a real leak still fails the teardown after the timeout.
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        busy = (getattr(host, "_active_jobs", {}).get(module_id)
                or getattr(host, "_job_leases", {}).get(module_id)
                or getattr(host, "_page_leases", {}).get(module_id))
        if not busy:
            return True
        app.processEvents()
        time.sleep(0.02)
    return False


def close_page(app, handle, page, host):
    page._busy = False
    host.close()
    page.deleteLater()
    app.processEvents()
    handle.close()
    wait_until_idle(app, host)


def test_page_runs_from_the_signed_package(runtime, app, tmp_path):
    handle, page, host = open_page(runtime, tmp_path)
    assert page.__class__.__module__.startswith("_studio_module_patterns_")
    assert [label.text() for label in page.step_labels][0].startswith("● 1.")
    assert page.next_button.isEnabled() and not page.back_button.isEnabled()
    close_page(app, handle, page, host)


def test_unfilled_steps_are_marked_and_every_step_opens_from_the_list(runtime, app, tmp_path, dialogs):
    handle, page, host = open_page(runtime, tmp_path, "unfilled")
    page._go_next()  # no files yet: «Далее» still moves on
    assert page._step == 1 and page.step_labels[0].text().startswith("✕ 1.")
    page.step_labels[3].clicked.emit()
    assert page._step == 3 and page.step_labels[3].text().startswith("● 4.")
    page.step_labels[0].clicked.emit()
    assert page._step == 0 and page.step_labels[0].text().startswith("● 1.")
    assert not dialogs
    close_page(app, handle, page, host)


def test_full_flow_from_pngs_to_exported_files(runtime, app, tmp_path, dialogs):
    handle, page, host = open_page(runtime, tmp_path)
    page._add_assets(make_pngs(tmp_path))
    assert len(page._assets) == 3 and page.next_button.isEnabled()
    page._add_assets(make_pngs(tmp_path))  # the same files again are not duplicated
    assert len(page._assets) == 3
    page._go_next()
    pump(app, lambda: not page._busy)
    page._settings["inches"] = 2.0  # keep the sheet small and the test fast
    page._invalidate(layout=True)
    page._go_next()
    pump(app, lambda: page._current is not None)
    assert page._current["seam"]["status"] == "ready" and page._current["image"].size == (600, 600)
    assert page.primary_action.text() == "Сохранить в набор" and page.next_button.isEnabled()
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
    assert again._assets == [] and again._project_id is None  # a new set starts empty
    assert [p["name"] for p in host.list_projects()] == ["Сохранённый"]
    assert again._open_project(host.list_projects()[0]["id"])
    assert len(again._assets) == 3 and again._settings["seed"] == 77 and again._settings["count"] == 9
    assert again._assets[0]["width"] == 200  # sizes come back from the stored files
    assert again.title.text() == "Patterns · Сохранённый"
    close_page(app, handle, again, host)


def test_saved_projects_can_be_deleted(runtime, app, tmp_path, dialogs, monkeypatch):
    from studio_patterns_page import ProjectsDialog
    handle, page, host = open_page(runtime, tmp_path, "delete")
    page._add_assets(make_pngs(tmp_path))
    page._settings.update(set_name="Лишний")
    page._go_next()
    project = host.list_projects()[0]
    dialog = ProjectsDialog(host, page._project_id, page)
    assert dialog.list.count() == 1
    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.StandardButton.No))
    dialog._delete()
    assert dialog.list.count() == 1
    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes))
    dialog._delete()
    assert dialog.list.count() == 0 and dialog.deleted_current
    assert host.list_projects() == [] and project["id"]
    close_page(app, handle, page, host)


def test_tile_mode_hides_unsupported_choices_and_fails_visibly(runtime, app, tmp_path, dialogs):
    handle, page, host = open_page(runtime, tmp_path)
    page._set_mode("tile")
    assert page.next_button.isEnabled() and page.pick_tile.isVisibleTo(page) and not page.add_files.isVisibleTo(page)
    cut = Image.new("RGB", (160, 120))
    ramp = ImageDraw.Draw(cut)
    for x in range(160):
        ramp.line((x, 0, x, 119), fill=(x * 255 // 159, 40, 200 - x))
    path = tmp_path / "tile.png"
    cut.save(path)
    page._tile = {**host.import_png(path), "name": "tile.png"}
    page._refresh()
    page._go_next()
    pump(app, lambda: not page._busy)
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


def test_step3_saves_the_sheet_and_offers_no_reroll(runtime, app, tmp_path, dialogs):
    handle, page, host = open_page(runtime, tmp_path)
    page._add_assets(make_pngs(tmp_path))
    page._settings["inches"] = 2.0
    page._go_next()
    pump(app, lambda: not page._busy)
    page._go_next()
    pump(app, lambda: page._current is not None)
    assert page.primary_action.text() == "Сохранить в набор" and not page.secondary_action.isVisibleTo(page)
    seed = page._settings["seed"]
    page.primary_action.click()
    assert page._step == 3 and page._settings["seed"] == seed
    pump(app, lambda: len(page._sheets) == page._settings['sheet_count'] and not page._busy)
    close_page(app, handle, page, host)


def test_step3_repeat_choice_grid_and_fullscreen(runtime, app, tmp_path, dialogs):
    handle, page, host = open_page(runtime, tmp_path)
    page._add_assets(make_pngs(tmp_path))
    page._settings["inches"] = 2.0
    page._go_next()
    pump(app, lambda: not page._busy)
    page._go_next()
    pump(app, lambda: page._current is not None)
    page.show()
    assert page._repeat == 5 and not page._grid
    import sys
    module = sys.modules[type(page).__module__]
    repeat_image = module.repeat_image
    flat = repeat_image(page._current["image"], 3)
    gridded = repeat_image(page._current["image"], 3, grid=True)
    assert flat.size == gridded.size and flat.tobytes() != gridded.tobytes()
    for count in (3, 4, 5, 6, 7):
        page.repeat_chips.changed.emit(str(count))
        assert page._repeat == count and repeat_image(page._current["image"], count).width % count == 0
    page.grid_box.setChecked(True)
    assert page._grid
    from unittest.mock import patch
    with patch.object(module.RepeatFullscreen, "exec", return_value=0) as opened:
        page.fullscreen_button.click()
        page.preview_picture.clicked.emit()
    assert opened.call_count == 2
    close_page(app, handle, page, host)


def test_step2_shows_a_live_sheet_that_follows_the_settings(runtime, app, tmp_path, dialogs):
    handle, page, host = open_page(runtime, tmp_path)
    page._add_assets(make_pngs(tmp_path))
    page._settings["inches"] = 2.0
    page._go_next()
    page.show()
    pump(app, lambda: page._current is not None and not page._busy)
    assert page.sheet_editor._pixmap is not None and page.sheet_editor.isVisibleTo(page)
    first = page._current["image"].tobytes()
    page._settings["gap"] = 120
    page._invalidate(layout=True)
    assert page._live_timer.isActive()  # the sheet redraws by itself shortly after a change
    page._live_timer.stop()
    page._live_render()
    pump(app, lambda: page._current is not None and not page._busy)
    assert page._current["image"].tobytes() != first
    close_page(app, handle, page, host)


def test_manual_edits_are_kept_on_reroll_and_can_be_reset(runtime, app, tmp_path, dialogs):
    handle, page, host = open_page(runtime, tmp_path)
    page._add_assets(make_pngs(tmp_path))
    page._settings.update(inches=2.0, count=6)
    page._go_next()
    pump(app, lambda: page._current is not None and not page._busy)
    first = page._elements[0]
    moved_to = {"x": 111.0, "y": 222.0, "scale": first["scale"], "angle": 15.0}
    page._element_edited(first["id"], moved_to)
    pump(app, lambda: page._current is not None and not page._busy)
    edited = next(e for e in page._elements if e["id"] == first["id"])
    assert edited["locked"] and (edited["x"], edited["y"]) == (111.0, 222.0)
    assert len(page._elements) == 6 and page.reset_edits.isEnabled()
    page._reroll()  # a new random layout leaves the hand-placed element where it is
    page._render_current()
    pump(app, lambda: page._current is not None and not page._busy)
    assert any(e["id"] == first["id"] and e["x"] == 111.0 for e in page._elements)
    count = len(page._elements)
    victim = next(e for e in page._elements if e["id"] != first["id"])
    page._element_deleted(victim["id"])
    pump(app, lambda: page._current is not None and not page._busy)
    assert len(page._elements) == count - 1
    page._reset_edits()
    pump(app, lambda: page._current is not None and not page._busy)
    assert not any(e.get("locked") for e in page._elements) and len(page._elements) == 6
    assert not page.reset_edits.isEnabled()
    close_page(app, handle, page, host)


def test_sheet_editor_picks_moves_resizes_rotates_and_deletes_with_the_mouse(app):
    from PyQt6.QtCore import QPointF, Qt
    from PyQt6.QtGui import QMouseEvent
    editor = SheetEditor()
    editor.resize(408, 408)
    editor.show()
    editor.set_sheet(Image.new("RGBA", (400, 400), (255, 255, 255, 255)),
                     [{"id": "a", "asset_id": "x", "x": 200.0, "y": 200.0, "scale": 1.0, "angle": 0.0, "locked": False, "z_index": 0}],
                     {"x": (100, 100)}, editable=True)
    seen = []
    editor.element_edited.connect(lambda i, v: seen.append(("edit", v)))
    editor.element_deleted.connect(lambda i: seen.append(("delete", i)))

    def mouse(kind, x, y):
        point = QPointF(x, y)
        event = QMouseEvent(kind, point, point, Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
        {QMouseEvent.Type.MouseButtonPress: editor.mousePressEvent, QMouseEvent.Type.MouseMove: editor.mouseMoveEvent,
         QMouseEvent.Type.MouseButtonRelease: editor.mouseReleaseEvent}[kind](event)

    press, move, release = QMouseEvent.Type.MouseButtonPress, QMouseEvent.Type.MouseMove, QMouseEvent.Type.MouseButtonRelease
    mouse(press, 10, 10)
    assert editor.selected_id is None
    mouse(press, 204, 204)
    assert editor.selected_id == "a"
    mouse(move, 254, 224)
    mouse(release, 254, 224)
    assert seen[-1][0] == "edit" and abs(seen[-1][1]["x"] - 250.0) < 1.5 and abs(seen[-1][1]["y"] - 220.0) < 1.5
    editor.set_sheet(Image.new("RGBA", (400, 400)), [{"id": "a", "asset_id": "x", "x": 200.0, "y": 200.0, "scale": 1.0, "angle": 0.0, "locked": False, "z_index": 0}],
                     {"x": (100, 100)}, editable=True)
    editor.select("a")
    corner = editor._to_view(250.0, 250.0)
    mouse(press, corner.x(), corner.y())
    far = editor._to_view(300.0, 300.0)
    mouse(move, far.x(), far.y())
    mouse(release, far.x(), far.y())
    assert seen[-1][1]["scale"] > 1.5
    editor.set_sheet(Image.new("RGBA", (400, 400)), [{"id": "a", "asset_id": "x", "x": 200.0, "y": 200.0, "scale": 1.0, "angle": 0.0, "locked": False, "z_index": 0}],
                     {"x": (100, 100)}, editable=True)
    editor.select("a")
    handle = editor._to_view(*editor._rotate_handle(editor._element("a")))
    mouse(press, handle.x(), handle.y())
    right = editor._to_view(300.0, 200.0)
    mouse(move, right.x(), right.y())
    mouse(release, right.x(), right.y())
    assert abs(seen[-1][1]["angle"] - 90.0) < 1.0
    editor.set_sheet(Image.new("RGBA", (400, 400)), [{"id": "a", "asset_id": "x", "x": 200.0, "y": 200.0, "scale": 1.0, "angle": 0.0, "locked": False, "z_index": 0}],
                     {"x": (100, 100)}, editable=True)
    editor.select("a")
    bin_centre = editor._bin_rect(editor._element("a")).center()
    mouse(press, bin_centre.x(), bin_centre.y())
    assert seen[-1] == ("delete", "a")
    editor.select("a")
    from PyQt6.QtTest import QTest
    QTest.keyClick(editor, Qt.Key.Key_Delete)
    assert seen[-1] == ("delete", "a")
    editor.set_sheet(Image.new("RGBA", (400, 400)), [], {}, editable=False)
    editor.close()


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
        # П2 (owner 2026-10-23): the Studio header names the open module, not «Автоматический клипарт».
        assert view.mode_selection.active_module_label.text() == "Паттерны"
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
    assert texts[1] == "tile.png · 600 × 400 px"
    assert not any("прозрачным фоном" in t for t in texts)
    assert page.pick_tile.text() == "Выбрать другой файл"
    close_page(app, handle, page, host)


def test_not_enough_room_message_is_russian_and_follows_the_slider(runtime, app, tmp_path):
    handle, page, host = open_page(runtime, tmp_path)
    page._add_assets(make_pngs(tmp_path))
    page._settings.update(inches=2.0, count=60, gap=300)
    page._go_next()
    pump(app, lambda: not page._busy)
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
    assert page.background_name.text() == "Свой цвет #0A78C8"
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
