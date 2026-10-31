"""PR-2 (макет drag-drop-png-20261030): дроп PNG на сетке проверки PNG.

Диалог: mime-фильтр PNG, цель — миниатюра под курсором, сигнал в flow.
Flow: валидация, номер позиции (явная цель > имя `_NN_ready` > диалог), копия
под шаблон позиции, подключение тем же механизмом recovery (версия, «Не
проверено», SET-0 не нарушен), отказы — красной плашкой на странице.
"""
import os
from pathlib import Path
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PIL import Image
from PyQt6.QtCore import QPointF, QUrl
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
    def __init__(self, files, point=QPointF(1, 1)):
        self._files = files
        self._point = point
        self.accepted = None

    def mimeData(self):
        return SimpleNamespace(urls=[QUrl.fromLocalFile(str(item)) for item in self._files])

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


def test_quality_drop_filters_txt_and_emits_target(app, tmp_path, monkeypatch):
    dialog, paths = quality_dialog(tmp_path)
    source = png(tmp_path / "from_explorer.png")
    seen = []
    dialog.files_dropped.connect(lambda files, target: seen.append((list(files), target)))
    monkeypatch.setattr(dialog.quality_list, "itemAt", lambda point: dialog.quality_list.item(1))
    dialog._quality_drop(FakeDropEvent([str(source), str(tmp_path / "notes.txt")]))
    assert seen == [([str(source)], str(paths[1].resolve()))]
    assert dialog.quality_drop_notice.isHidden()


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


def test_flow_attaches_dropped_file_and_keeps_version(app, tmp_path):
    session = make_session(tmp_path)
    notices = []
    stub = make_flow_stub(session, notices)
    source = tmp_path / "from_explorer_03_ready.png"
    Image.new("RGBA", (24, 24), (10, 200, 90, 255)).save(source)  # уникальный контент — не дубль
    auto_flow.AutoClipartFlowController._attach_dropped_to_png_check(stub, [str(source)], None)
    item = session.items[2]
    assert Path(item.output_path).name == "from_explorer_03_ready_03_ready.png"
    assert Path(item.output_path).parent == Path(session.output_dir)
    assert (item.review_mark, item.review_checked) == ("ok", False)
    assert item.short_message == "PNG подключён перетаскиванием."
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
    assert all(item.short_message != "PNG подключён перетаскиванием." for item in session.items)


def test_flow_duplicate_drop_reports_the_position(app, tmp_path):
    session = make_session(tmp_path)
    notices = []
    stub = make_flow_stub(session, notices)
    duplicate = png(tmp_path / "duplicate_source.png")  # байты совпадают с картинками фикстуры
    target = session.items[0].output_path
    auto_flow.AutoClipartFlowController._attach_dropped_to_png_check(stub, [str(duplicate)], target)
    assert any("уже показывает этот файл" in notice for notice in notices)
    assert session.items[0].output_path == target  # позиция не тронута


def test_flow_busy_shows_notice_and_does_not_touch_session(app, tmp_path):
    session = make_session(tmp_path)
    notices = []
    stub = make_flow_stub(session, notices, busy=True)
    source = png(tmp_path / "busy_02_ready.png")
    before = session.items[1].output_path
    auto_flow.AutoClipartFlowController._attach_dropped_to_png_check(stub, [str(source)], None)
    assert session.items[1].output_path == before
    assert any("Идёт обработка" in notice for notice in notices)
