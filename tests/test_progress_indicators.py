from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PIL import Image
from PyQt6.QtWidgets import QApplication

from v3_processing_flow import ProcessingFilesPage
from v3_project_state import ProjectMode, ProjectState


_APP = None


def _page(app):
    state = ProjectState(mode=ProjectMode.PROCESSING)
    return ProcessingFilesPage(state, lambda: None) if _takes_callback() else ProcessingFilesPage(state)


def _takes_callback():
    import inspect
    return len(inspect.signature(ProcessingFilesPage.__init__).parameters) > 2


def test_adding_many_files_shows_progress_then_hides(tmp_path):
    app = QApplication.instance() or QApplication([])
    paths = []
    for index in range(8):
        path = tmp_path / f"i{index}.png"
        Image.new("RGBA", (20, 20), (index * 20, 0, 0, 255)).save(path)
        paths.append(str(path))
    page = _page(app)
    seen = []
    original = page._progress_step

    def spy(shown, done, total, text):
        if shown:
            seen.append((done, total, text, page.add_progress.isVisibleTo(page), page.add_status.text()))
        original(shown, done, total, text)

    page._progress_step = spy
    accepted = page.add_files(paths)
    assert len(accepted) == 8
    assert seen, "progress must be reported for a large batch"
    assert all(item[3] for item in seen)                      # bar was visible while working
    assert any(item[2] == "Проверяю файлы" for item in seen)
    assert any(item[2] == "Показываю изображения" for item in seen)
    assert page.add_progress.isHidden() and page.add_status.isHidden()  # gone afterwards
    assert page._progress_depth == 0


def test_small_batch_does_not_flash_a_progress_bar(tmp_path):
    app = QApplication.instance() or QApplication([])
    path = tmp_path / "a.png"
    Image.new("RGBA", (20, 20), "red").save(path)
    page = _page(app)
    page.add_files([str(path)])
    assert page.add_progress.isHidden()


def test_export_reports_each_set_through_progress_callback(tmp_path):
    from studio_set_export import export_clipart_sets
    sources = []
    for index in range(2):
        path = tmp_path / f"p{index}.png"
        Image.new("RGBA", (20, 20), "red").save(path)
        sources.append(str(path))
    dest = tmp_path / "out"
    dest.mkdir()
    events = []
    export_clipart_sets([{"title": "A", "images": sources[:1]}, {"title": "B", "images": sources[1:]}],
                        dest, progress=lambda done, total, text: events.append((done, total, text)))
    assert [e[:2] for e in events] == [(0, 2), (1, 2), (2, 2)]
    assert events[0][2].startswith("Создаю набор 1 из 2")


def test_export_dialog_shows_and_hides_progress_bar(tmp_path):
    from PyQt6.QtWidgets import QApplication as App
    from studio_set_export_ui import SetExportDialog
    global _APP
    _APP = App.instance() or App([])
    path = tmp_path / "a.png"
    Image.new("RGBA", (20, 20), "red").save(path)
    dialog = SetExportDialog([path])
    assert dialog.export_progress.isHidden()
    dialog._export_progress(1, 4, "Создаю набор 2 из 4")
    assert dialog.export_progress.maximum() == 4 and dialog.export_progress.value() == 1
    assert "Создаю набор 2 из 4" in dialog.status.text()
    dialog._export_progress(0, 0, "Перевожу названия на английский…")
    assert dialog.export_progress.maximum() == 0  # indeterminate (moving) bar
    dialog.reject()
