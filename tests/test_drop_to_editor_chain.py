"""Цепочка владелицы: перетащить картинки из папки → в набор → отметка → двойной клик → редактор прозрачности.

Все шаги проверяются настоящими событиями Qt (QDragEnterEvent/QDropEvent с QMimeData из файлов,
QMouseEvent двойного клика), а не вызовом обработчика напрямую: в offscreen `QTest.mouseDClick`
не шлёт DblClick, поэтому события собираются вручную.
"""
import os
from pathlib import Path
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PIL import Image
from PyQt6.QtCore import QEvent, QMimeData, QPointF, Qt, QUrl
from PyQt6.QtGui import QDragEnterEvent, QDropEvent, QMouseEvent
from PyQt6.QtWidgets import QApplication, QMessageBox

import studio_auto_clipart_flow as auto_flow
from studio_alpha_qc import AlphaQcReport
from studio_set_export_ui import SetExportDialog
from v3_processing_flow import ProcessingFilesPage
from v3_project_state import ProjectMode, ProjectState
from v3_run_queue import RunItem, RunItemStatus, RunResultsPage
from tests.test_studio_set_export_drop import make_flow_stub, make_session, png, quality_dialog


@pytest.fixture(scope="module")
def app():
    yield QApplication.instance() or QApplication([])


def real_drop(widget, files, point):
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(str(item)) for item in files])
    actions = Qt.DropAction.CopyAction
    args = (actions, mime, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
    enter = QDragEnterEvent(point, *args)
    QApplication.sendEvent(widget, enter)
    drop = QDropEvent(QPointF(point), *args)
    QApplication.sendEvent(widget, drop)
    return enter, drop


def mouse(kind, point, buttons=Qt.MouseButton.LeftButton):
    return QMouseEvent(kind, QPointF(point), QPointF(point), Qt.MouseButton.LeftButton, buttons,
                       Qt.KeyboardModifier.NoModifier)


def real_double_click(widget, point):
    """Нажатие, отпускание, второе нажатие как DblClick, отпускание — так Qt доставляет двойной клик."""
    for kind, buttons in ((QEvent.Type.MouseButtonPress, Qt.MouseButton.LeftButton),
                          (QEvent.Type.MouseButtonRelease, Qt.MouseButton.NoButton),
                          (QEvent.Type.MouseButtonDblClick, Qt.MouseButton.LeftButton),
                          (QEvent.Type.MouseButtonRelease, Qt.MouseButton.NoButton)):
        QApplication.sendEvent(widget, mouse(kind, point, buttons))


def test_files_page_takes_new_pictures_dropped_from_a_folder(app, tmp_path):
    first, second = png(tmp_path / "a.png"), png(tmp_path / "b.png")
    state = ProjectState(mode=ProjectMode.PROCESSING)
    page = ProcessingFilesPage(state, lambda: None)
    page.show()
    enter, drop = real_drop(page.viewport(), [first, second], page.viewport().rect().center())
    assert enter.isAccepted() and drop.isAccepted()
    assert [Path(info.path).name for info in page.file_infos] == ["a.png", "b.png"]
    page.close()


def test_files_page_takes_a_drop_onto_its_inner_widgets(app, tmp_path):
    """Бросают не на край страницы, а на область списка/кнопку: событие должно дойти до страницы."""
    picture = png(tmp_path / "inner.png")
    state = ProjectState(mode=ProjectMode.PROCESSING)
    page = ProcessingFilesPage(state, lambda: None)
    page.resize(700, 600)
    page.show()
    app.processEvents()
    target = page.choose_button
    enter, drop = real_drop(target, [picture], target.rect().center())
    assert drop.isAccepted()
    assert [Path(info.path).name for info in page.file_infos] == ["inner.png"]
    page.close()


def test_quality_grid_double_click_asks_for_the_transparency_editor(app, tmp_path):
    dialog, paths = quality_dialog(tmp_path)
    dialog.show()
    asked = []
    dialog.fix_requested.connect(asked.append)
    viewport = dialog.quality_list.viewport()
    point = dialog.quality_list.visualItemRect(dialog.quality_list.item(1)).center()
    real_double_click(viewport, point.toPointF().toPoint() if hasattr(point, "toPointF") else point)
    assert asked == [str(paths[1].resolve())]
    dialog.reject()


def test_quality_grid_double_click_while_busy_explains_why(app, tmp_path):
    dialog, paths = quality_dialog(tmp_path)
    dialog.show()
    dialog.worker = object()
    asked = []
    dialog.fix_requested.connect(asked.append)
    point = dialog.quality_list.visualItemRect(dialog.quality_list.item(0)).center()
    real_double_click(dialog.quality_list.viewport(), point)
    assert asked == []
    assert not dialog.quality_drop_notice.isHidden()
    assert "обработ" in dialog.quality_drop_notice.text().lower()
    dialog.worker = None
    dialog.reject()


def test_sets_table_double_click_asks_for_the_transparency_editor(app, tmp_path):
    paths = [png(tmp_path / f"s_{index}.png") for index in range(3)]
    dialog = SetExportDialog(paths)
    dialog.show()
    asked = []
    dialog.fix_requested.connect(asked.append)
    app.processEvents()
    point = dialog.table.visualItemRect(dialog.table.item(1, 0)).center()
    real_double_click(dialog.table.viewport(), point)
    expected = str(Path(dialog.table.item(1, 0).data(Qt.ItemDataRole.UserRole)).resolve())
    assert asked == [expected]
    dialog.reject()


def test_whole_chain_drop_mark_double_click(app, tmp_path):
    """Бросили картинку на сетку → она подключилась к позиции → отметили «Ок» → двойной клик открывает редактор."""
    session = make_session(tmp_path)
    notices = []
    stub = make_flow_stub(session, notices)
    fresh = tmp_path / "from_folder_02_ready.png"
    Image.new("RGBA", (24, 24), (250, 10, 90, 255)).save(fresh)

    outputs = [Path(item.output_path) for item in session.items]
    reports = [AlphaQcReport(str(path.resolve()), "ok", (), width=8, height=8) for path in outputs]
    dialog = SetExportDialog(outputs, quality_reports=reports)
    dialog.enable_marks({str(path.resolve()): "unchecked" for path in outputs})
    dialog._show_quality_review()
    dialog.show()
    dropped = []
    dialog.files_dropped.connect(lambda files, target: dropped.append((list(files), target)))
    dialog.files_dropped.connect(
        lambda files, target: auto_flow.AutoClipartFlowController._attach_dropped_to_png_check(
            stub, files, target))
    marks = []
    dialog.mark_requested.connect(lambda key, mark: marks.append((key, mark)))
    asked = []
    dialog.fix_requested.connect(asked.append)

    point = dialog.quality_list.visualItemRect(dialog.quality_list.item(1)).center()
    _enter, drop = real_drop(dialog.quality_list.viewport(), [fresh], point)
    assert drop.isAccepted() and dropped == [([str(fresh)], str(outputs[1].resolve()))]
    assert session.items[1].short_message == "PNG подключён перетаскиванием."

    dialog.quality_list.setCurrentRow(1)
    dialog.quality_mark_buttons["ok"].click()
    assert marks == [(str(outputs[1].resolve()), "ok")]

    real_double_click(dialog.quality_list.viewport(), point)
    assert asked == [str(outputs[1].resolve())]
    dialog.reject()


def _results_page(items):
    page = RunResultsPage(ProjectState(mode=ProjectMode.CLIPART))
    page.session = SimpleNamespace(items=items, running=False)
    return page


def _capture_messages(monkeypatch):
    shown = []
    monkeypatch.setattr(QMessageBox, "information", lambda *args, **kwargs: shown.append(args[2]))
    return shown


def test_run_page_fix_without_a_session_tells_the_owner(app, tmp_path, monkeypatch):
    shown = _capture_messages(monkeypatch)
    page = RunResultsPage(ProjectState(mode=ProjectMode.CLIPART))
    page._request_quality_fix(str(png(tmp_path / "x.png")))
    assert len(shown) == 1 and "запуск" in shown[0].lower()
    page.close()


def test_run_page_fix_for_an_unknown_file_tells_the_owner(app, tmp_path, monkeypatch):
    shown = _capture_messages(monkeypatch)
    known = png(tmp_path / "known.png")
    page = _results_page([RunItem(1, "x", status=RunItemStatus.SUCCEEDED, output_path=str(known),
                                  payload={"result_kind": "clipart"})])
    opened = []
    page.transparency_requested.connect(opened.append)
    page._request_quality_fix(str(png(tmp_path / "stranger.png").resolve()))
    assert opened == [] and len(shown) == 1 and "stranger.png" in shown[0]
    page.close()


def test_run_page_fix_finds_the_edited_copy_of_a_position(app, tmp_path, monkeypatch):
    shown = _capture_messages(monkeypatch)
    original, edited = png(tmp_path / "o.png"), png(tmp_path / "o_edited.png")
    page = _results_page([RunItem(1, "x", status=RunItemStatus.SUCCEEDED, output_path=str(original),
                                  editor_output_path=str(edited), payload={"result_kind": "clipart"})])
    opened = []
    page.transparency_requested.connect(opened.append)
    page._request_quality_fix(str(edited.resolve()))
    assert opened == [0] and shown == []
    page.close()


def test_run_page_fix_while_running_tells_the_owner(app, tmp_path, monkeypatch):
    shown = _capture_messages(monkeypatch)
    known = png(tmp_path / "known.png")
    page = _results_page([RunItem(1, "x", status=RunItemStatus.SUCCEEDED, output_path=str(known),
                                  payload={"result_kind": "clipart"})])
    page.session.running = True
    opened = []
    page.transparency_requested.connect(opened.append)
    page._request_quality_fix(str(known.resolve()))
    assert opened == [] and len(shown) == 1 and "обработ" in shown[0].lower()
    page.close()
