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


def real_drop(widget, files, point, modifiers=Qt.KeyboardModifier.NoModifier):
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(str(item)) for item in files])
    actions = Qt.DropAction.CopyAction
    args = (actions, mime, Qt.MouseButton.LeftButton, modifiers)
    enter = QDragEnterEvent(point, *args)
    QApplication.sendEvent(widget, enter)
    drop = QDropEvent(QPointF(point), *args)
    QApplication.sendEvent(widget, drop)
    return enter, drop


def window_drop(widget, files, child, modifiers=Qt.KeyboardModifier.NoModifier):
    """Бросок через окно, как из проводника: Qt сам ищет под курсором виджет, который принимает дроп."""
    top = widget.window()
    point = child.mapTo(top, child.rect().center())
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(str(item)) for item in files])
    args = (Qt.DropAction.CopyAction, mime, Qt.MouseButton.LeftButton, modifiers)
    QApplication.sendEvent(top.windowHandle(), QDragEnterEvent(point, *args))
    drop = QDropEvent(QPointF(point), *args)
    QApplication.sendEvent(top.windowHandle(), drop)
    return drop


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


def _wired_dialog(session, stub, results_page):
    """Сетка «Проверка PNG» по текущим картинкам набора; дроп идёт в тот же обработчик, что в приложении."""
    outputs = results_page._review_paths()
    reports = [AlphaQcReport(str(path), "ok", (), width=8, height=8) for path in outputs]
    dialog = SetExportDialog(outputs, quality_reports=reports)
    dialog.enable_marks({str(path): "unchecked" for path in outputs})
    dialog._show_quality_review()
    dialog.show()
    dialog.files_dropped.connect(
        lambda files, target: auto_flow.AutoClipartFlowController._attach_dropped_to_png_check(
            stub, files, target))
    return dialog, outputs


def test_whole_chain_drop_adds_position_mark_double_click_edit_export(app, tmp_path):
    """Бросили файл из папки → позиций стало больше → «Ок» → двойной клик → редактор → сохранение → в экспорте."""
    session = make_session(tmp_path)
    page = RunResultsPage(ProjectState(mode=ProjectMode.CLIPART))
    page.session = session
    stub = make_flow_stub(session, [])
    fresh = tmp_path / "from_folder_02_ready.png"
    Image.new("RGBA", (24, 24), (250, 10, 90, 255)).save(fresh)
    dialog, outputs = _wired_dialog(session, stub, page)
    originals = [item.output_path for item in session.items]

    point = dialog.quality_list.visualItemRect(dialog.quality_list.item(1)).center()
    _enter, drop = real_drop(dialog.quality_list.viewport(), [fresh], point)
    assert drop.isAccepted()
    assert len(session.items) == 5, "позиций стало больше"
    assert [item.output_path for item in session.items[:4]] == originals, "картинка позиции 2 не заменена"
    added = session.items[4]
    assert added.display_name == "from_folder_02_ready"
    assert (added.review_mark, added.review_checked) == ("ok", False)
    new_path = Path(added.output_path).resolve()
    assert new_path in page._review_paths()
    assert new_path not in page._export_paths(), "не проверено — в экспорт ещё не идёт"
    dialog.reject()

    dialog, outputs = _wired_dialog(session, stub, page)
    key = str(new_path)
    row = outputs.index(new_path)
    marks = []
    dialog.mark_requested.connect(lambda path, mark: marks.append((path, mark)))
    dialog.quality_list.setCurrentRow(row)
    dialog.quality_mark_buttons["ok"].click()
    assert marks == [(key, "ok")]
    added.review_checked = True  # так «Ок» записывает проверка PNG
    assert new_path in page._export_paths()

    asked = []
    dialog.fix_requested.connect(asked.append)
    opened = []
    page.transparency_requested.connect(opened.append)
    real_double_click(dialog.quality_list.viewport(), dialog.quality_list.visualItemRect(
        dialog.quality_list.item(row)).center())
    assert asked == [key]
    page._request_quality_fix(asked[0])
    assert opened == [4], "редактор прозрачности открывается для новой позиции"

    edited = png(tmp_path / "output" / "from_folder_02_ready_05_ready_edited.png")
    page.use_edited_output(new_path, edited)
    assert added.editor_output_path == str(edited.resolve())
    assert edited.resolve() in page._export_paths(), "правка сохранена и попадает в экспорт"
    dialog.reject()


def test_whole_chain_shift_drop_on_a_picture_replaces_only_that_one(app, tmp_path):
    session = make_session(tmp_path)
    page = RunResultsPage(ProjectState(mode=ProjectMode.CLIPART))
    page.session = session
    stub = make_flow_stub(session, [])
    fresh = tmp_path / "explicit.png"
    Image.new("RGBA", (24, 24), (7, 77, 177, 255)).save(fresh)
    dialog, outputs = _wired_dialog(session, stub, page)
    originals = [item.output_path for item in session.items]
    point = dialog.quality_list.visualItemRect(dialog.quality_list.item(1)).center()
    _enter, drop = real_drop(dialog.quality_list.viewport(), [fresh], point, Qt.KeyboardModifier.ShiftModifier)
    assert drop.isAccepted()
    assert len(session.items) == 4
    assert session.items[1].output_path != originals[1]
    assert [item.output_path for index, item in enumerate(session.items) if index != 1] == \
        [path for index, path in enumerate(originals) if index != 1]
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


# --- расширение 2026-11-01: «Результаты» и «Наборы» принимают файлы тем же механизмом ---

def unique_png(path, shade):
    path = Path(path)
    Image.new("RGBA", (24, 24), (shade, 20, 200 - shade, 255)).save(path)
    return path


def _stub_with_page(session, notices, page):
    stub = make_flow_stub(session, notices)
    stub.run_queue.page = page
    stub._show_drop_notice_on_panel = lambda text: (notices.append(text), page.show_drop_notice(text))
    return stub


def _attach(stub):
    return lambda paths: auto_flow.AutoClipartFlowController._attach_dropped_to_png_check(stub, paths, None)


def test_results_page_drop_adds_a_position_and_shows_refusals(app, tmp_path):
    session = make_session(tmp_path)
    page = RunResultsPage(ProjectState(mode=ProjectMode.CLIPART))
    page.session = session
    notices = []
    stub = _stub_with_page(session, notices, page)
    page._drop_filter = auto_flow.FileDropFilter(page, _attach(stub))
    page.resize(700, 600)
    page.show()
    app.processEvents()
    fresh = unique_png(tmp_path / "results_drop.png", 11)
    note = tmp_path / "note.txt"
    note.write_text("x")
    drop = window_drop(page, [fresh, note], page.queue.viewport())
    assert drop.isAccepted()
    assert len(session.items) == 5, notices
    assert session.items[4].display_name == "results_drop"
    assert Path(session.items[4].output_path).resolve() in page._review_paths()
    assert not page.drop_notice.isHidden()
    assert "позиции 5" in page.drop_notice.text() and "note.txt" in page.drop_notice.text()
    page.close()


def test_sets_page_drop_adds_then_ok_gives_set_checkboxes_and_export_takes_the_ticks(app, tmp_path):
    session = make_session(tmp_path)
    page = RunResultsPage(ProjectState(mode=ProjectMode.CLIPART))
    page.session = session
    notices = []
    stub = _stub_with_page(session, notices, page)
    paths = [Path(item.output_path).resolve() for item in session.items]
    dialog = SetExportDialog(paths)
    dialog.files_dropped.connect(lambda files, target: None)
    dialog._drop_filter = auto_flow.FileDropFilter(dialog, _attach(stub))
    dialog.show()
    app.processEvents()
    assert dialog.stack.currentWidget() is dialog.summary_page
    fresh = unique_png(tmp_path / "sets_drop.png", 22)
    drop = window_drop(dialog, [fresh], dialog.table.viewport())
    assert drop.isAccepted()
    assert len(session.items) == 5
    added = session.items[4]
    assert (added.review_mark, added.review_checked) == ("ok", False)
    dialog.reject()

    added.review_checked = True  # «Ок» в проверке PNG
    new_path = Path(added.output_path).resolve()
    assert new_path in page._export_paths()
    outputs = page._export_paths()
    dialog = SetExportDialog(outputs)
    dialog.show()
    app.processEvents()
    row = next(r for r in range(dialog.table.rowCount())
               if Path(dialog.table.item(r, 0).data(Qt.ItemDataRole.UserRole)).resolve() == new_path)
    assert dialog.table.columnCount() >= 2, "у картинки есть галочки наборов"
    dialog.table.item(row, 1).setCheckState(Qt.CheckState.Checked)
    ticked = [link["included"] for link in dialog._membership()[str(new_path)]["memberships"]]
    assert ticked and ticked[0] is True
    included = [str(Path(p).resolve()) for group in dialog.groups(dialog._membership()) for p in group["images"]]
    assert str(new_path) in included, "экспорт набора включает отмеченную картинку"
    dialog.reject()


def test_redo_of_a_dropped_picture_says_there_is_no_prompt(app, tmp_path):
    session = make_session(tmp_path)
    notices = []
    stub = make_flow_stub(session, notices)
    stub._queue_redo = lambda kind, path: pytest.fail("переделка не должна стартовать")
    stub.review = SimpleNamespace(regenerate_path=lambda path: pytest.fail("переделка не должна стартовать"))
    fresh = unique_png(tmp_path / "no_prompt.png", 33)
    auto_flow.AutoClipartFlowController._attach_dropped_to_png_check(stub, [str(fresh)], None)
    dropped = Path(session.items[4].output_path)
    auto_flow.AutoClipartFlowController._regenerate_from_png_check(stub, str(dropped))
    assert notices[-1] == auto_flow.NO_PROMPT_TEXT
    # обычная позиция по-прежнему идёт в переделку
    started = []
    stub._queue_redo = lambda kind, path: False
    stub.review = SimpleNamespace(regenerate_path=lambda path: started.append(path) or object())
    stub._show_redo_progress = lambda: None
    auto_flow.AutoClipartFlowController._regenerate_from_png_check(stub, session.items[0].output_path)
    assert started == [session.items[0].output_path]


def test_redo_button_in_the_png_check_grid_for_a_dropped_picture_shows_the_message(app, tmp_path):
    session = make_session(tmp_path)
    page = RunResultsPage(ProjectState(mode=ProjectMode.CLIPART))
    page.session = session
    notices = []
    stub = _stub_with_page(session, notices, page)
    stub._queue_redo = lambda kind, path: pytest.fail("не должна стартовать")
    stub.review = SimpleNamespace(regenerate_path=lambda path: pytest.fail("не должна стартовать"))
    fresh = unique_png(tmp_path / "grid_redo.png", 44)
    auto_flow.AutoClipartFlowController._attach_dropped_to_png_check(stub, [str(fresh)], None)
    outputs = page._review_paths()
    dialog = SetExportDialog(outputs, quality_reports=[AlphaQcReport(str(p), "ok", (), width=8, height=8)
                                                       for p in outputs])
    dialog.enable_marks({str(p): "unchecked" for p in outputs})
    dialog.regenerate_requested.connect(
        lambda path: auto_flow.AutoClipartFlowController._regenerate_from_png_check(stub, path))
    dialog._show_quality_review()
    dialog.show()
    app.processEvents()
    dialog.quality_list.setCurrentRow(len(outputs) - 1)
    dialog.quality_mark_buttons["bad_generation"].click()
    dialog.quality_regenerate_button.click()
    assert notices and notices[-1] == auto_flow.NO_PROMPT_TEXT
    assert not page.drop_notice.isHidden()
    dialog.reject()
    page.close()


def test_review_redo_selection_with_a_dropped_picture_says_there_is_no_prompt(app, tmp_path, monkeypatch):
    from studio_clipart_review_ui import ImageReview
    session = make_session(tmp_path)
    notices = []
    stub = make_flow_stub(session, notices)
    auto_flow.AutoClipartFlowController._attach_dropped_to_png_check(stub, [str(unique_png(tmp_path / "sel.png", 55))], None)
    shown = _capture_messages(monkeypatch)
    page = SimpleNamespace(queue=SimpleNamespace(selected_rows=lambda: [4]))
    stub.run_queue = SimpleNamespace(session=session, page=page,
                                     regenerate_selected=lambda rows: pytest.fail("не должна стартовать"))
    stub.refuse_redo_of_dropped = lambda sess, rows: auto_flow.AutoClipartFlowController.refuse_redo_of_dropped(stub, sess, rows)
    review = SimpleNamespace(session=session, flow=stub, _pending_cutout=[], _chain_started=False)
    ImageReview.regenerate_selected_rows(review)
    assert notices[-1] == auto_flow.NO_PROMPT_TEXT and shown == []
