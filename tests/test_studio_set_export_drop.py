"""PR-2 (макет drag-drop-png-20261030): дроп PNG на сетке проверки PNG.

Диалог: mime-фильтр PNG, цель — миниатюра под курсором, сигнал в flow.
Правило владелицы (2026-11-01): бросок из папки ДОБАВЛЯЕТ новую позицию; заменить картинку
можно только явно — Shift + бросок точно на неё. Flow: валидация, копия под шаблон позиции,
«Не проверено», отказы — красной плашкой на странице.
"""
import os
from pathlib import Path
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PIL import Image
from PyQt6.QtCore import QPointF, Qt, QUrl
from PyQt6.QtWidgets import QApplication

import studio_auto_clipart_flow as auto_flow
from studio_alpha_qc import AlphaQcReport
from studio_set_export_ui import SetExportDialog
from v3_clipart_flow import ClipartRunRequest
from v3_project_state import ProjectMode
from v3_run_queue import RunQueueSession, RunItemStatus


@pytest.fixture(scope="module")
def app():
    yield QApplication.instance() or QApplication([])


def png(path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGBA", (24, 24), (120, 160, 200, 255)).save(path)
    return path


def quality_dialog(tmp_path, count=3):
    paths = [png(tmp_path / f"gosling_{index + 1:02d}_ready.png") for index in range(count)]
    reports = [AlphaQcReport(str(path.resolve()), "ok", (), width=8, height=8) for path in paths]
    dialog = SetExportDialog(paths, quality_reports=reports)
    dialog._show_quality_review()
    return dialog, paths


class FakeDropEvent:
    def __init__(self, files, point=QPointF(1, 1), modifiers=Qt.KeyboardModifier.NoModifier):
        self._files = files
        self._point = point
        self._modifiers = modifiers
        self.accepted = None

    def modifiers(self):
        return self._modifiers

    def mimeData(self):
        urls = [QUrl.fromLocalFile(str(item)) for item in self._files]
        return SimpleNamespace(urls=lambda: urls)

    def position(self):
        return self._point

    def acceptProposedAction(self):
        self.accepted = True

    def ignore(self):
        self.accepted = False


def make_session(tmp_path, count=4):
    request = ClipartRunRequest(
        mode="mode1_generate_only", work_dir=str(tmp_path),
        settings={"output_dir": str(tmp_path / "output")},
        generated_prompts=[{"prompt": f"object {index}", "references": [], "object_id": f"o{index}"}
                           for index in range(count)])
    session = RunQueueSession(request, ProjectMode.CLIPART)
    for index, item in enumerate(session.items):
        item.status = RunItemStatus.SUCCEEDED
        item.output_path = str(png(Path(tmp_path / "output" / f"gosling_{index + 1:02d}_ready.png")))
    session.running = False
    return session


def make_flow_stub(session, notices, busy=False):
    return SimpleNamespace(
        run_queue=SimpleNamespace(session=session, page=SimpleNamespace(refresh_from_state=lambda: None)),
        is_busy=lambda: busy,
        _save_run=lambda: None,
        _show_drop_notice_on_panel=notices.append,
    )


def test_quality_drop_filters_txt_and_adds_without_target(app, tmp_path, monkeypatch):
    dialog, paths = quality_dialog(tmp_path)
    source = png(tmp_path / "from_explorer.png")
    seen = []
    dialog.files_dropped.connect(lambda files, target: seen.append((list(files), target)))
    monkeypatch.setattr(dialog.quality_list, "itemAt", lambda point: dialog.quality_list.item(1))
    dialog._quality_drop(FakeDropEvent([str(source), str(tmp_path / "notes.txt")]))
    assert seen == [([str(source)], None)], "без Shift цели нет: файл добавляется новой позицией"
    assert dialog.quality_drop_notice.isHidden()


def test_quality_drop_with_shift_on_a_picture_names_it_as_the_target(app, tmp_path, monkeypatch):
    dialog, paths = quality_dialog(tmp_path)
    source = png(tmp_path / "from_explorer.png")
    seen = []
    dialog.files_dropped.connect(lambda files, target: seen.append((list(files), target)))
    monkeypatch.setattr(dialog.quality_list, "itemAt", lambda point: dialog.quality_list.item(1))
    dialog._quality_drop(FakeDropEvent([str(source)], modifiers=Qt.KeyboardModifier.ShiftModifier))
    assert seen == [([str(source)], str(paths[1].resolve()))]


def test_quality_drop_with_shift_beside_pictures_adds(app, tmp_path, monkeypatch):
    dialog, _ = quality_dialog(tmp_path)
    source = png(tmp_path / "from_explorer.png")
    seen = []
    dialog.files_dropped.connect(lambda files, target: seen.append((list(files), target)))
    monkeypatch.setattr(dialog.quality_list, "itemAt", lambda point: None)
    dialog._quality_drop(FakeDropEvent([str(source)], modifiers=Qt.KeyboardModifier.ShiftModifier))
    assert seen == [([str(source)], None)]


def test_quality_drop_without_png_is_ignored(app, tmp_path):
    dialog, _ = quality_dialog(tmp_path)
    seen = []
    dialog.files_dropped.connect(lambda *args: seen.append(args))
    event = FakeDropEvent([str(tmp_path / "notes.txt")])
    dialog._quality_drop(event)
    assert event.accepted is False
    assert seen == []


def test_show_drop_notice_toggles_and_resets_on_refresh(app, tmp_path):
    dialog, _ = quality_dialog(tmp_path)
    dialog.show_drop_notice("Позиция 2: уже показывает этот файл.")
    assert not dialog.quality_drop_notice.isHidden()
    dialog._refresh_quality_page()
    assert dialog.quality_drop_notice.isHidden()


def test_flow_adds_dropped_file_as_a_new_position(app, tmp_path):
    session = make_session(tmp_path)
    notices = []
    stub = make_flow_stub(session, notices)
    before = [item.output_path for item in session.items]
    source = tmp_path / "from_explorer_03_ready.png"
    Image.new("RGBA", (24, 24), (10, 200, 90, 255)).save(source)  # уникальный контент — не дубль
    auto_flow.AutoClipartFlowController._attach_dropped_to_png_check(stub, [str(source)], None)
    assert len(session.items) == 5
    assert [item.output_path for item in session.items[:4]] == before, "прежние позиции не тронуты"
    item = session.items[4]
    assert (item.index, item.display_name) == (5, "from_explorer_03_ready")
    assert item.status is RunItemStatus.SUCCEEDED
    assert Path(item.output_path).name == "from_explorer_03_ready_05_ready.png"
    assert Path(item.output_path).parent == Path(session.output_dir)
    assert (item.review_mark, item.review_checked) == ("ok", False)
    assert item.short_message == "PNG подключён перетаскиванием."
    assert item.payload.get("dropped") is True
    assert not (Path(session.output_dir) / "versions").exists(), "версий нет: ничего не заменялось"
    assert any("Добавлено" in notice and "5" in notice for notice in notices), notices


def test_flow_adds_every_dropped_file_in_order(app, tmp_path):
    session = make_session(tmp_path, count=2)
    stub = make_flow_stub(session, [])
    first, second = tmp_path / "first.png", tmp_path / "second.png"
    Image.new("RGBA", (24, 24), (1, 2, 3, 255)).save(first)
    Image.new("RGBA", (24, 24), (4, 5, 6, 255)).save(second)
    auto_flow.AutoClipartFlowController._attach_dropped_to_png_check(stub, [str(first), str(second)], None)
    assert [item.display_name for item in session.items[2:]] == ["first", "second"]
    assert [item.index for item in session.items] == [1, 2, 3, 4]


def test_flow_shift_drop_on_a_picture_replaces_it_and_keeps_the_version(app, tmp_path):
    session = make_session(tmp_path)
    notices = []
    stub = make_flow_stub(session, notices)
    source = tmp_path / "from_explorer.png"
    Image.new("RGBA", (24, 24), (10, 200, 90, 255)).save(source)
    target = session.items[2].output_path
    auto_flow.AutoClipartFlowController._attach_dropped_to_png_check(stub, [str(source)], target)
    assert len(session.items) == 4, "позиций не стало больше"
    item = session.items[2]
    assert Path(item.output_path).name == "from_explorer_03_ready.png"
    assert (item.review_mark, item.review_checked) == ("ok", False)
    assert list((Path(session.output_dir) / "versions").glob("*")), "прежняя картинка позиции 3 ушла в версии"
    assert any("позиции 3" in notice for notice in notices)


def test_flow_rejects_folders_with_a_reason(app, tmp_path):
    session = make_session(tmp_path)
    notices = []
    stub = make_flow_stub(session, notices)
    folder = tmp_path / "folder"
    folder.mkdir()
    auto_flow.AutoClipartFlowController._attach_dropped_to_png_check(stub, [str(folder)], None)
    assert any("папк" in notice.lower() for notice in notices)
    assert len(session.items) == 4


def test_flow_rejects_non_png_with_a_reason(app, tmp_path):
    session = make_session(tmp_path)
    notices = []
    stub = make_flow_stub(session, notices)
    text = tmp_path / "notes.txt"
    text.write_text("не картинка")
    auto_flow.AutoClipartFlowController._attach_dropped_to_png_check(stub, [str(text)], None)
    assert len(session.items) == 4
    assert any("notes.txt" in notice for notice in notices), notices


def test_flow_duplicate_drop_adds_nothing_and_reports_the_position(app, tmp_path):
    session = make_session(tmp_path)
    notices = []
    stub = make_flow_stub(session, notices)
    duplicate = png(tmp_path / "duplicate_source.png")  # байты совпадают с картинками фикстуры
    before = _output_files(session)
    auto_flow.AutoClipartFlowController._attach_dropped_to_png_check(stub, [str(duplicate)], None)
    assert len(session.items) == 4
    assert any("уже есть" in notice and "позиции 1" in notice for notice in notices), notices
    assert _output_files(session) == before, "копия-сирота не осталась"


def test_flow_busy_shows_notice_and_does_not_touch_session(app, tmp_path):
    session = make_session(tmp_path)
    notices = []
    stub = make_flow_stub(session, notices, busy=True)
    source = png(tmp_path / "busy_02_ready.png")
    auto_flow.AutoClipartFlowController._attach_dropped_to_png_check(stub, [str(source)], None)
    assert len(session.items) == 4
    assert any("Идёт обработка" in notice for notice in notices)


def _output_files(session):
    return sorted(path.name for path in Path(session.output_dir).glob("*.png"))


def test_flow_copy_failure_is_reported_and_does_not_stop_the_other_files(app, tmp_path, monkeypatch):
    """Антивирус/Windows держит файл или нет места: дроп не должен падать исключением из слота Qt."""
    session = make_session(tmp_path)
    notices = []
    stub = make_flow_stub(session, notices)
    locked = tmp_path / "locked_01_ready.png"
    Image.new("RGBA", (24, 24), (11, 22, 33, 255)).save(locked)
    fine = tmp_path / "fine_02_ready.png"
    Image.new("RGBA", (24, 24), (44, 55, 66, 255)).save(fine)
    real_copy = auto_flow.copy_for_position

    def flaky_copy(source, output_dir, number):
        if Path(source).name == locked.name:
            raise PermissionError(32, "Процесс не может получить доступ к файлу")
        return real_copy(source, output_dir, number)

    monkeypatch.setattr(auto_flow, "copy_for_position", flaky_copy)
    auto_flow.AutoClipartFlowController._attach_dropped_to_png_check(stub, [str(locked), str(fine)], None)
    assert len(session.items) == 5, "добавлен только второй файл"
    assert session.items[4].display_name == "fine_02_ready"
    assert any(locked.name in notice and "не удалось" in notice.lower() for notice in notices), notices


def test_flow_version_failure_on_replace_leaves_no_orphan_copy(app, tmp_path, monkeypatch):
    session = make_session(tmp_path)
    notices = []
    stub = make_flow_stub(session, notices)
    source = tmp_path / "fresh_03_ready.png"
    Image.new("RGBA", (24, 24), (9, 99, 199, 255)).save(source)

    def broken_keep_version(item, output_dir):
        raise OSError("версию сохранить нельзя")

    monkeypatch.setattr("studio_clipart_versions.keep_version", broken_keep_version)
    before = _output_files(session)
    target = session.items[2].output_path
    auto_flow.AutoClipartFlowController._attach_dropped_to_png_check(stub, [str(source)], target)
    assert _output_files(session) == before
    assert session.items[2].output_path == target
    assert any("не подключ" in notice for notice in notices)


def test_flow_limit_of_files_stays(app, tmp_path):
    session = make_session(tmp_path, count=1)
    notices = []
    stub = make_flow_stub(session, notices)
    files = []
    for number in range(9):
        path = tmp_path / f"many_{number}.png"
        Image.new("RGBA", (24, 24), (number * 20, 5, 5, 255)).save(path)
        files.append(str(path))
    auto_flow.AutoClipartFlowController._attach_dropped_to_png_check(stub, files, None)
    assert len(session.items) == 1 + 8, "лимит дропа 8 файлов остался"
    assert any("лишние" in notice for notice in notices), notices


def _real_drop(widget, files, point):
    """Настоящие QMimeData + QDropEvent, отправленные во viewport, как делает Qt при дропе из проводника."""
    from PyQt6.QtCore import QMimeData, Qt
    from PyQt6.QtGui import QDragEnterEvent, QDropEvent

    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(str(item)) for item in files])
    actions = Qt.DropAction.CopyAction
    enter = QDragEnterEvent(point, actions, mime, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
    QApplication.sendEvent(widget, enter)
    drop = QDropEvent(QPointF(point), actions, mime, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
    QApplication.sendEvent(widget, drop)
    return enter, drop


def test_quality_grid_real_drop_of_several_files_reaches_flow(app, tmp_path):
    dialog, paths = quality_dialog(tmp_path)
    dialog.show()
    first = png(tmp_path / "a.png")
    second = png(tmp_path / "b.png")
    seen = []
    dialog.files_dropped.connect(lambda files, target: seen.append((list(files), target)))
    viewport = dialog.quality_list.viewport()
    rect = dialog.quality_list.visualItemRect(dialog.quality_list.item(1))
    enter, drop = _real_drop(viewport, [first, second], rect.center())
    assert enter.isAccepted() and drop.isAccepted()
    assert seen == [([str(first), str(second)], None)]


def test_other_drop_targets_still_take_real_events(app, tmp_path):
    from PyQt6.QtCore import QPoint
    from studio_reference_editor import ReferenceEditor
    editor = ReferenceEditor.__new__(ReferenceEditor)  # only the drop handlers are under test
    added = []
    editor.add_reference = added.append
    editor.status = SimpleNamespace(setText=lambda text: None)
    first, second = png(tmp_path / "r1.png"), png(tmp_path / "r2.png")
    from PyQt6.QtCore import QMimeData, Qt
    from PyQt6.QtGui import QDropEvent
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(str(first)), QUrl.fromLocalFile(str(second))])
    drop = QDropEvent(QPointF(QPoint(1, 1)), Qt.DropAction.CopyAction, mime,
                      Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
    ReferenceEditor.dropEvent(editor, drop)
    assert added == [str(first), str(second)]
