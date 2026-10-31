"""Auto Clipart owner review: marks, notes, versions, trash and cut-out redo."""
import os
from datetime import datetime
from pathlib import Path
from unittest.mock import Mock

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PIL import Image
from PyQt6.QtWidgets import QApplication, QMessageBox, QSizePolicy

from studio_auto_clipart_state import AutoClipartStateExtension
from studio_clipart_versions import (
    discard_last_version, empty_trash, keep_version, restore_review, restore_version,
    review_fields, trash_paths, validate_review_row, versions_dir,
)
from v3_clipart_flow import ClipartRunRequest
from v3_project_state import CommonProjectData, ProjectMode, ProjectState
from v3_run_queue import RunItem, RunItemStatus, RunQueueSession, RunQueueSupport, RunResultsPage

NOW = datetime(2026, 10, 22, 14, 5)


@pytest.fixture(scope="module", autouse=True)
def app():
    return QApplication.instance() or QApplication([])


def png(path, colour=(200, 40, 40, 255)):
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGBA", (8, 8), colour).save(path)
    return path


def item_with_output(tmp_path, name="goose_ready.png", colour=(200, 40, 40, 255)):
    item = RunItem(index=1, display_name=name, status=RunItemStatus.SUCCEEDED)
    item.output_path = str(png(tmp_path / "output" / name, colour))
    return item


def pixel(path):
    with Image.open(path) as image:
        return image.getpixel((0, 0))


# --- saved format ------------------------------------------------------------

def test_default_review_is_not_written_so_old_projects_stay_unchanged(tmp_path):
    item = item_with_output(tmp_path)
    assert review_fields(item) == {}
    validate_review_row({})


def test_review_round_trips_through_saved_row(tmp_path):
    item = item_with_output(tmp_path)
    item.review_mark, item.review_note = "bad_generation", "лишняя лапа"
    keep_version(item, tmp_path / "output", "goose prompt", now=NOW)
    item.review_mark = "deleted"
    row = review_fields(item)
    validate_review_row(row)
    copy = RunItem(index=1, display_name="x")
    restore_review(copy, row)
    assert (copy.review_mark, copy.review_note, copy.versions) == ("deleted", "", item.versions)


@pytest.mark.parametrize("row", [
    {"review_mark": "maybe"},
    {"review_note": "x" * 501},
    {"versions": "nope"},
    {"versions": [{"path": "a"}]},
    {"versions": [{"path": "a", "original": "", "reason": "lost", "note": "", "prompt": "", "created": ""}]},
    {"versions": [{"path": "", "original": "", "reason": "ok", "note": "", "prompt": "", "created": ""}]},
])
def test_malformed_review_is_refused(row):
    with pytest.raises(ValueError):
        validate_review_row(row)


def test_project_state_accepts_review_fields_and_refuses_bad_ones():
    base = {"status": "succeeded", "output_path": "", "attempts": 1}
    extension = AutoClipartStateExtension()
    good = {"clipart": {"automatic": {"run": [dict(base, review_mark="bad_cutout", review_note="кайма")]}}}
    assert extension.normalize_state(good) is good
    bad = {"clipart": {"automatic": {"run": [dict(base, review_mark="unknown")]}}}
    with pytest.raises(ValueError):
        extension.normalize_state(bad)
    # Archived runs are validated by the same rules.
    archived = {"clipart": {"automatic": {"previous_runs": [{
        "prompts": [{"prompt": "p", "references": [], "result_kind": "clipart", "object_id": "o1"}],
        "run": [dict(base, review_note=5)]}]}}}
    with pytest.raises(ValueError):
        extension.normalize_state(archived)


# --- versions -------------------------------------------------------------------

def test_keep_version_copies_picture_and_moves_mark_and_note(tmp_path):
    item = item_with_output(tmp_path)
    item.review_mark, item.review_note = "bad_generation", "кривой клюв"
    assert keep_version(item, tmp_path / "output", "old prompt", now=NOW)
    entry = item.versions[0]
    assert Path(entry["path"]).parent == (tmp_path / "output" / "versions").resolve()
    assert Path(entry["path"]).name == "goose_ready.v1.png"
    assert (entry["reason"], entry["note"], entry["prompt"]) == ("bad_generation", "кривой клюв", "old prompt")
    assert Path(item.output_path).is_file()  # copied, not moved
    assert (item.review_mark, item.review_note) == ("ok", "")


def test_keep_version_without_current_picture_does_nothing(tmp_path):
    item = RunItem(index=1, display_name="x", status=RunItemStatus.FAILED)
    assert not keep_version(item, tmp_path / "output")
    assert item.versions == []


def test_restore_version_swaps_current_and_old(tmp_path):
    output = tmp_path / "output"
    item = item_with_output(tmp_path, colour=(1, 1, 1, 255))
    keep_version(item, output, now=NOW)
    png(Path(item.output_path), (2, 2, 2, 255))  # the new attempt replaced the file
    restore_version(item, 0, output, now=NOW)
    assert pixel(item.output_path) == (1, 1, 1, 255)
    assert len(item.versions) == 1
    assert pixel(item.versions[0]["path"]) == (2, 2, 2, 255)


def _lock_restore_target(monkeypatch):
    """An antivirus holds the picture: replacing it fails with WinError 32."""
    real = Path.replace

    def locked(self, target):
        if str(self).endswith(".restore"):
            raise PermissionError(13, "The process cannot access the file", None, 32)
        return real(self, target)

    monkeypatch.setattr(Path, "replace", locked)


def _files(root):
    return sorted(path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_file())


def test_restore_under_a_locked_picture_changes_nothing(tmp_path, monkeypatch):
    output = tmp_path / "output"
    item = item_with_output(tmp_path, colour=(1, 1, 1, 255))
    keep_version(item, output, now=NOW)
    png(Path(item.output_path), (2, 2, 2, 255))
    item.review_mark, item.review_note, item.review_checked = "bad_generation", "кривой клюв", True
    versions, files = [dict(entry) for entry in item.versions], _files(output)
    _lock_restore_target(monkeypatch)
    with pytest.raises(PermissionError):
        restore_version(item, 0, output, now=NOW)
    assert item.versions == versions
    assert (item.review_mark, item.review_note, item.review_checked) == ("bad_generation", "кривой клюв", True)
    assert _files(output) == files  # no .restore leftovers, no extra version, the old one is still there
    assert pixel(item.output_path) == (2, 2, 2, 255)


def test_restore_can_be_repeated_after_the_lock_is_gone(tmp_path, monkeypatch):
    output = tmp_path / "output"
    item = item_with_output(tmp_path, colour=(1, 1, 1, 255))
    keep_version(item, output, now=NOW)
    png(Path(item.output_path), (2, 2, 2, 255))
    with monkeypatch.context() as locked:
        _lock_restore_target(locked)
        with pytest.raises(PermissionError):
            restore_version(item, 0, output, now=NOW)
    restore_version(item, 0, output, now=NOW)
    assert pixel(item.output_path) == (1, 1, 1, 255)
    assert [pixel(entry["path"]) for entry in item.versions] == [(2, 2, 2, 255)]


def test_restore_still_succeeds_when_the_spent_version_file_is_locked(tmp_path, monkeypatch):
    output = tmp_path / "output"
    item = item_with_output(tmp_path, colour=(1, 1, 1, 255))
    keep_version(item, output, now=NOW)
    png(Path(item.output_path), (2, 2, 2, 255))
    spent = Path(item.versions[0]["path"])
    real = Path.unlink

    def locked_unlink(self, *args, **kwargs):
        if self == spent:
            raise PermissionError(13, "in use", None, 32)
        return real(self, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", locked_unlink)
    restore_version(item, 0, output, now=NOW)
    assert pixel(item.output_path) == (1, 1, 1, 255)
    assert [pixel(entry["path"]) for entry in item.versions] == [(2, 2, 2, 255)]


def test_restore_after_failed_recreation_uses_recorded_original(tmp_path):
    output = tmp_path / "output"
    item = item_with_output(tmp_path, colour=(1, 1, 1, 255))
    original = item.output_path
    keep_version(item, output, now=NOW)
    Path(original).unlink()
    item.output_path = ""
    restore_version(item, 0, output, now=NOW)
    assert item.output_path == str(Path(original).resolve())
    assert pixel(original) == (1, 1, 1, 255)
    assert item.versions == []


def test_restore_refuses_unrecorded_or_outside_version(tmp_path):
    output = tmp_path / "output"
    item = item_with_output(tmp_path)
    item.versions = [{"path": str(png(tmp_path / "elsewhere.png")), "original": item.output_path,
                      "reason": "ok", "note": "", "prompt": "", "created": ""}]
    with pytest.raises(ValueError):
        restore_version(item, 0, output)
    with pytest.raises(ValueError):
        restore_version(item, 5, output)


def test_version_symlink_is_never_restored(tmp_path):
    output = tmp_path / "output"
    item = item_with_output(tmp_path)
    keep_version(item, output, now=NOW)
    target = Path(item.versions[0]["path"])
    target.unlink()
    target.symlink_to(png(tmp_path / "secret.png"))
    with pytest.raises(ValueError):
        restore_version(item, 0, output)


def test_discard_last_version_removes_only_its_recorded_file(tmp_path):
    output = tmp_path / "output"
    item = item_with_output(tmp_path)
    keep_version(item, output, now=NOW)
    path = Path(item.versions[0]["path"])
    discard_last_version(item, output)
    assert not path.exists() and item.versions == []
    assert Path(item.output_path).is_file()


# --- trash ------------------------------------------------------------------------

def test_empty_trash_deletes_only_deleted_pictures_and_recorded_versions(tmp_path):
    output = tmp_path / "output"
    kept = item_with_output(tmp_path, "teddy_ready.png")
    keep_version(kept, output, now=NOW)
    deleted = item_with_output(tmp_path, "cup_ready.png")
    deleted.review_mark = "deleted"
    stray = png(versions_dir(output) / "unrelated.png")
    outside = png(tmp_path / "outside_ready.png")
    foreign = item_with_output(tmp_path, "foreign_ready.png")
    foreign.output_path = str(outside)
    foreign.review_mark = "deleted"  # outside the result folder: never deleted
    items = [kept, deleted, foreign]
    removed_pictures, removed_versions = trash_paths(items, output)
    assert len(removed_pictures) == 1 and len(removed_versions) == 1
    assert empty_trash(items, output) == 2
    assert Path(kept.output_path).is_file() and kept.versions == []
    assert deleted.output_path == "" and deleted.review_mark == "deleted"
    assert stray.is_file() and outside.is_file()


# --- run queue -------------------------------------------------------------------

def generation_session(tmp_path, count=2):
    request = ClipartRunRequest(
        mode="mode1_generate_only", work_dir=str(tmp_path), settings={"output_dir": str(tmp_path / "output")},
        generated_prompts=[{"prompt": f"object {index}", "references": [], "object_id": f"o{index}"}
                           for index in range(count)])
    session = RunQueueSession(request, ProjectMode.CLIPART)
    for index, item in enumerate(session.items):
        item.status = RunItemStatus.SUCCEEDED
        item.output_path = str(png(tmp_path / "output" / f"object{index}_ready.png"))
    session.running = False
    return session


def test_only_explicitly_accepted_pictures_are_in_export_sets(tmp_path):
    state = ProjectState(mode=ProjectMode.CLIPART, common=CommonProjectData(work_dir=str(tmp_path)))
    page = RunResultsPage(state)
    session = generation_session(tmp_path, count=5)
    accepted, unchecked, generation_defect, cutout_defect, deleted = session.items
    accepted.review_mark, accepted.review_checked = "ok", True
    unchecked.review_mark, unchecked.review_checked = "ok", False
    generation_defect.review_mark, generation_defect.review_checked = "bad_generation", True
    cutout_defect.review_mark, cutout_defect.review_checked = "bad_cutout", True
    deleted.review_mark, deleted.review_checked = "deleted", True
    page.set_session(session)
    assert page._export_paths() == [Path(accepted.output_path).resolve()]
    page.deleteLater()


def test_reprocess_uses_saved_raw_generation_without_new_generation(tmp_path):
    session = generation_session(tmp_path)
    assert session.reprocessable_indices([0, 1]) == []  # no raw source recorded yet
    raw = png(session.transient_dir / "rough_object0.png", (0, 0, 255, 255))
    session.items[0].source_path = str(raw)
    outside = png(tmp_path / "rough_outside.png")
    session.items[1].source_path = str(outside)  # not in the run's own folder
    assert session.reprocessable_indices([0, 1]) == [0]
    request = session.preview_reprocess([0, 1], {"remove_bg_provider": "local_chroma_key",
                                                  "chroma_subject_profile": "legacy"})
    assert request.mode == "mode2_process" and request.generated_prompts == []
    assert request.selected_files == [str(raw.resolve())]
    assert request.settings["chroma_subject_profile"] == "legacy"
    assert request.settings["skip_remover_for_alpha"] is False
    assert request.settings["publish_recovered_source"] is True
    assert request.settings["task_item_indices"] == [1]
    session.prepare_reprocess([0])
    item = session.items[0]
    assert item.status is RunItemStatus.PENDING and item.output_path == ""
    assert item.source_path == str(raw)
    assert item.stage_statuses == {"generation": "complete"}


def test_recreation_keeps_versions_through_controller_hook(tmp_path):
    session = generation_session(tmp_path)
    raw = png(session.transient_dir / "rough_object0.png")
    session.items[0].source_path = str(raw)
    controller = Mock()
    controller.is_busy.return_value = False
    controller.worker = None
    support = RunQueueSupport.__new__(RunQueueSupport)
    support.controller = controller
    support.session = session
    started = []
    support._start_worker = lambda _worker, request: started.append(request) or request
    support.reprocess_selected([0], {"remove_bg_provider": "local_chroma_key"})
    controller.before_replace_outputs.assert_called_once_with([0], "reprocess")
    assert started and started[0].mode == "mode2_process"
    # A refused paid confirmation starts nothing and keeps no version.
    session.running = False
    controller.reset_mock()
    started.clear()
    session.items[0].status = RunItemStatus.SUCCEEDED
    support.reprocess_selected([0], {"remove_bg_provider": "kie"}, confirm=lambda _request: False)
    controller.before_replace_outputs.assert_not_called()
    assert started == []


def test_failed_version_hook_stops_recreation(tmp_path):
    session = generation_session(tmp_path)
    controller = Mock()
    controller.is_busy.return_value = False
    controller.worker = None
    controller.confirm_retry_request.return_value = True
    controller.before_replace_outputs.side_effect = ValueError("Папка версий недоступна")
    support = RunQueueSupport.__new__(RunQueueSupport)
    support.controller = controller
    support.session = session
    assert support.regenerate_selected([0]) is None
    controller._error.assert_called_once_with("Папка версий недоступна")
    assert session.items[0].status is RunItemStatus.SUCCEEDED
    assert session.running is False


def test_refused_regeneration_is_journaled_with_its_reason(tmp_path):
    """Owner 2026-10-27: a regeneration refused before the run left no trace in the diagnostics."""
    session = generation_session(tmp_path)
    session.items[0].status = RunItemStatus.SUCCEEDED
    journal = Mock()
    session._diagnostic_journal = journal
    controller = Mock()
    controller.is_busy.return_value = False
    controller.worker = None
    controller.confirm_retry_request.return_value = True
    controller.before_replace_outputs.side_effect = ValueError("Папка версий недоступна")
    support = RunQueueSupport.__new__(RunQueueSupport)
    support.controller = controller
    support.session = session
    assert support.regenerate_selected([0]) is None
    call = journal.record.call_args
    assert call.args[0] == "regenerate_blocked" and call.kwargs["severity"] == "error"
    assert call.kwargs["details"]["reason"] == "keep_versions_failed"
    controller.confirm_retry_request.return_value = False
    assert support.regenerate_selected([0]) is None
    assert journal.record.call_args.kwargs["details"]["reason"] == "not_confirmed"


def test_results_list_shows_marks_and_filters_rows(tmp_path):
    from studio_clipart_review_ui import annotation, visible
    state = ProjectState(mode=ProjectMode.CLIPART, common=CommonProjectData(work_dir=str(tmp_path)))
    page = RunResultsPage(state)
    session = generation_session(tmp_path)
    session.items[1].review_mark, session.items[1].review_note = "deleted", "не подходит"
    page.queue.annotate = annotation
    page.queue.row_visible = lambda item: visible(item, "deleted")
    page.set_session(session)
    assert "Удалено · ✎ не подходит" in page.queue.item(1).text()
    assert page.queue.item(0).text().endswith("Не проверено")  # «Ок» only after the owner looked
    assert page.queue.item(0).isHidden() and not page.queue.item(1).isHidden()
    page.deleteLater()


# --- transparency window strip -----------------------------------------------------

class FakeFlow:
    def __init__(self, session, state):
        from types import SimpleNamespace
        self.saved = 0
        page = RunResultsPage(state)
        page.set_session(session)
        self.run_queue = SimpleNamespace(session=session, page=page, reprocess_selected=Mock(return_value=None),
                                         regenerate_selected=Mock(return_value=None),
                                         upscale_redo_selected=Mock(return_value=None))
        self.shell = SimpleNamespace(mark_dirty=lambda: None, state=state)

    def _save_run(self):
        self.saved += 1

    def is_busy(self):
        return False


def open_review(tmp_path):
    from studio_clipart_review_ui import ImageReview
    from v3_transparency_preview import ClipartTransparencyEditorPage
    state = ProjectState(mode=ProjectMode.CLIPART, common=CommonProjectData(work_dir=str(tmp_path)))
    session = generation_session(tmp_path)
    flow = FakeFlow(session, state)
    review = ImageReview(flow)
    review.install_results_page()
    editor = ClipartTransparencyEditorPage()
    paths = [Path(item.output_path) for item in session.items]
    editor.set_files(paths, selected_index=0)
    review.attach_editor(editor, paths)
    return review, editor, session, flow


def test_marks_and_note_are_saved_from_the_strip(tmp_path):
    review, editor, session, flow = open_review(tmp_path)
    strip = review.strip
    strip.mark_buttons["bad_generation"].click()
    assert session.items[0].review_mark == "bad_generation"
    assert strip.prompt_button.isVisibleTo(strip) and not strip.try_button.isVisibleTo(strip)
    strip.note.setText("лишняя лапа")
    strip.note.editingFinished.emit()
    assert session.items[0].review_note == "лишняя лапа"
    review.flush_save()
    assert flow.saved >= 1
    assert "Брак генерации · ✎ заметка" in editor.file_list.item(0).text()
    editor.deleteLater()


def test_deleted_mark_shows_notice_and_restore(tmp_path):
    review, editor, session, flow = open_review(tmp_path)
    review.strip.mark_buttons["deleted"].click()
    assert editor._canvas_notice.isVisibleTo(editor)
    assert review.strip.restore_button.isVisibleTo(review.strip)
    review.strip.restore_button.click()
    assert session.items[0].review_mark == "ok"
    assert not editor._canvas_notice.isVisibleTo(editor)
    editor.deleteLater()


def test_bad_cutout_without_raw_source_offers_brush_or_generation(tmp_path):
    review, editor, session, flow = open_review(tmp_path)
    review.strip.mark_buttons["bad_cutout"].click()
    strip = review.strip
    # «Исправить кистью» and «Отметить как брак генерации» are gone from the strip (owner 2026-10-27).
    assert not strip.to_generation_button.isVisibleTo(strip) and not strip.brush_button.isVisibleTo(strip)
    assert not strip.try_button.isVisibleTo(strip)
    assert not strip.status.isVisibleTo(strip) and "Исходная картинка" in strip.toolTip()
    strip.mark_buttons["bad_generation"].click()
    assert session.items[0].review_mark == "bad_generation"
    editor.deleteLater()


# --- folder files no position owns (owner 2026-10-31: «метки не реагируют») --------

def open_review_after_folder_load(tmp_path, monkeypatch):
    """The owner's path: «Ещё» → «Вернуть готовые файлы», then «Проверка PNG».

    Position 1 keeps its picture; position 2 arrives from the folder. The folder also
    holds files no position can own: a number beyond the set, a name without a number
    and an older copy of the occupied position 1.
    """
    from types import MethodType, SimpleNamespace

    from studio_auto_clipart_flow import AutoClipartFlowController
    from v3_run_queue import transparency_candidate_paths

    request = ClipartRunRequest(
        mode="mode1_generate_only", work_dir=str(tmp_path),
        settings={"output_dir": str(tmp_path / "output")},
        generated_prompts=[{"prompt": "goose", "references": [], "object_id": "o0"},
                           {"prompt": "cat", "references": [], "object_id": "o1"}])
    session = RunQueueSession(request, ProjectMode.CLIPART)
    session.items[0].status = RunItemStatus.SUCCEEDED
    session.items[0].output_path = str(png(tmp_path / "output" / "goose_01_ready.png"))
    session.items[0].review_mark, session.items[0].review_checked = "ok", True
    session.running = False  # item 1: interrupted, its PNG lies in the folder
    for name in ("cat_02_ready.png", "far_09_ready.png", "gift_ready.png"):
        png(tmp_path / "output" / name, (40, 200, 40, 255))
    old = png(tmp_path / "output" / "goose_01_ready_2.png", (40, 40, 200, 255))
    os.utime(old, (1_000, 1_000))  # older copy: position 1 shows the newer file

    state = ProjectState(mode=ProjectMode.CLIPART, common=CommonProjectData(work_dir=str(tmp_path)))
    state.data = SimpleNamespace(automatic={})  # what the real shell keeps project data in
    flow = FakeFlow(session, state)
    monkeypatch.setattr(
        "studio_auto_clipart_flow.QMessageBox.question",
        staticmethod(lambda *args, **kwargs: QMessageBox.StandardButton.Yes))
    flow.recover_results = MethodType(AutoClipartFlowController.recover_results, flow)
    flow._recoverable_outputs = MethodType(AutoClipartFlowController._recoverable_outputs, flow)
    flow.recover_results()
    assert session.items[1].output_path.endswith("cat_02_ready.png")  # подключение сработало

    from studio_clipart_review_ui import ImageReview
    from v3_transparency_preview import ClipartTransparencyEditorPage
    review = ImageReview(flow)
    review.install_results_page()
    editor = ClipartTransparencyEditorPage()
    paths = transparency_candidate_paths(session)
    editor.set_files(paths, selected_index=0)
    review.attach_editor(editor, paths)
    return review, editor, session, flow


def row_of(editor, name):
    return next(index for index, path in enumerate(editor._paths) if path.name == name)


def test_a_folder_file_without_a_position_explains_its_dead_marks(tmp_path, monkeypatch):
    """«Просто не реагирует» — больше нет: файл без позиции говорит, почему метки мертвы."""
    review, editor, session, flow = open_review_after_folder_load(tmp_path, monkeypatch)
    editor.file_list.setCurrentRow(row_of(editor, "gift_ready.png"))
    notice = editor._canvas_notice
    assert notice is not None and notice.isVisibleTo(editor), "объяснение должно быть видно на холсте"
    assert "не подключён" in notice.text()
    strip = review.strip
    assert not strip.mark_buttons["ok"].isEnabled() and not strip.mark_buttons["bad_generation"].isEnabled()
    assert "не подключён" in strip.toolTip()
    editor.deleteLater()


def test_unconnected_files_are_labelled_in_the_check_list(tmp_path, monkeypatch):
    """В списке видно, какая картинка без позиции, — наравне с подписями меток."""
    review, editor, session, flow = open_review_after_folder_load(tmp_path, monkeypatch)
    assert "не подключён" in editor.file_list.item(row_of(editor, "far_09_ready.png")).text()
    assert "не подключён" in editor.file_list.item(row_of(editor, "goose_01_ready_2.png")).text()
    assert "Не проверено" in editor.file_list.item(row_of(editor, "cat_02_ready.png")).text()
    editor.deleteLater()


def test_a_connected_picture_hides_the_not_connected_notice(tmp_path, monkeypatch):
    """Объяснение показано только у файла без позиции; подключённая картинка метится как раньше."""
    review, editor, session, flow = open_review_after_folder_load(tmp_path, monkeypatch)
    editor.file_list.setCurrentRow(row_of(editor, "gift_ready.png"))
    assert editor._canvas_notice.isVisibleTo(editor)
    editor.file_list.setCurrentRow(row_of(editor, "goose_01_ready.png"))
    assert not editor._canvas_notice.isVisibleTo(editor)
    strip = review.strip
    assert strip.mark_buttons["ok"].isEnabled()
    strip.mark_buttons["ok"].click()
    assert session.items[0].review_mark == "ok" and session.items[0].review_checked is True
    editor.deleteLater()


def test_marks_of_an_unconnected_file_cannot_leak_into_the_run(tmp_path, monkeypatch):
    """Негативный контроль: метки без позиции не появляются ни у одной записи запуска (SET-0)."""
    review, editor, session, flow = open_review_after_folder_load(tmp_path, monkeypatch)
    before = [(item.review_mark, item.review_checked, item.output_path) for item in session.items]
    for name in ("far_09_ready.png", "gift_ready.png", "goose_01_ready_2.png"):
        editor.file_list.setCurrentRow(row_of(editor, name))
        for mark in ("ok", "bad_generation", "bad_cutout", "deleted"):
            review.strip.mark_buttons[mark].click()  # кнопки мертвы: клик ничего не меняет
        review._set_mark("ok")  # и сам обработчик метку не ставит
    after = [(item.review_mark, item.review_checked, item.output_path) for item in session.items]
    assert after == before
    confirmed = {Path(path).name for path in flow.run_queue.page._export_paths()}
    assert confirmed == {"goose_01_ready.png"}
    editor.deleteLater()


def test_the_not_connected_notice_does_not_leak_onto_a_connected_picture(tmp_path, monkeypatch):
    """Даже во время пересоздания соседней картинки объяснение не висит над подключённой."""
    review, editor, session, flow = open_review_after_folder_load(tmp_path, monkeypatch)
    editor.file_list.setCurrentRow(row_of(editor, "gift_ready.png"))
    assert editor._canvas_notice.isVisibleTo(editor)
    review._job = object()  # идёт пересоздание: полоса выключена, список жив
    editor.file_list.setCurrentRow(row_of(editor, "cat_02_ready.png"))
    assert not editor._canvas_notice.isVisibleTo(editor)
    editor.deleteLater()


def test_try_cutout_starts_free_redo_from_raw_source(tmp_path):
    review, editor, session, flow = open_review(tmp_path)
    session.items[0].source_path = str(png(session.transient_dir / "rough_object0.png"))
    review.strip.mark_buttons["bad_cutout"].click()
    assert review.strip.try_button.isVisibleTo(review.strip)
    review.strip.try_button.click()
    args, kwargs = flow.run_queue.reprocess_selected.call_args
    assert args[0] == [0] and args[1]["remove_bg_provider"] == "local_chroma_key"
    assert kwargs["confirm"](None) is True  # free method: no paid confirmation
    assert review._job is None and editor.isEnabled()  # nothing started (mock returned None)
    editor.deleteLater()


def test_version_restore_from_editor_reloads_file(tmp_path):
    review, editor, session, flow = open_review(tmp_path)
    item = session.items[0]
    original = pixel(item.output_path)
    keep_version(item, session.output_dir, now=NOW)
    png(Path(item.output_path), (9, 9, 9, 255))
    review._restore(0, 0)
    assert pixel(item.output_path) == original
    assert item.status is RunItemStatus.SUCCEEDED and len(item.versions) == 1
    editor.deleteLater()


def test_results_bar_counts_marked_and_trash(tmp_path):
    review, editor, session, flow = open_review(tmp_path)
    session.items[0].review_mark = "bad_generation"
    session.items[1].review_mark = "deleted"
    flow.run_queue.page.refresh_from_state()
    assert review.recreate_button.text() == "Пересоздать помеченные (1)"
    assert review.trash_button.text() == "Корзина (1)"
    assert review.results_filter.itemText(1).startswith("Не проверено")
    assert review.results_filter.itemText(2) == "Помеченные (2)"
    editor.deleteLater()


def test_recreated_picture_takes_the_previous_name(tmp_path):
    review, editor, session, flow = open_review(tmp_path)
    item = session.items[0]
    previous = Path(item.output_path).resolve()
    review.before_replace_outputs([0], "reprocess")
    review.session_changed()  # a save before the run starts must not rename anything
    session.running = True
    review.session_changed()
    new = png(session.output_dir / "gen_001_20261022_ready.png", (5, 5, 5, 255))
    item.output_path = str(new)
    session.running = False
    review.session_changed()
    assert item.output_path == str(previous) and not new.exists()
    assert pixel(previous) == (5, 5, 5, 255)
    assert len(item.versions) == 1 and pixel(item.versions[0]["path"]) == (200, 40, 40, 255)
    editor.deleteLater()


def test_failed_recreation_keeps_previous_file_untouched(tmp_path):
    review, editor, session, flow = open_review(tmp_path)
    item = session.items[0]
    previous = Path(item.output_path)
    review.before_replace_outputs([0], "regenerate")
    session.running = True
    review.session_changed()
    item.status, item.output_path = RunItemStatus.FAILED, ""
    session.running = False
    review.session_changed()
    assert previous.is_file() and item.output_path == ""
    editor.deleteLater()


def test_chroma_receipt_follows_the_renamed_picture(tmp_path):
    from chroma_provenance import receipt_path
    review, editor, session, flow = open_review(tmp_path)
    item = session.items[0]
    previous = Path(item.output_path).resolve()
    receipt_path(previous).write_text("old", encoding="utf-8")
    review.before_replace_outputs([0], "reprocess")
    session.running = True
    review.session_changed()
    new = png(session.output_dir / "gen_001_ready.png")
    receipt_path(new).write_text("new", encoding="utf-8")
    item.output_path = str(new)
    session.running = False
    review.session_changed()
    assert receipt_path(previous).read_text(encoding="utf-8") == "new"
    assert not receipt_path(new).exists()
    editor.deleteLater()


def test_marked_filter_keeps_every_row_and_the_filter_bar_during_a_run(tmp_path):
    """Regression (owner, 2026-10-25): a regenerated picture loses its mark, so with «Помеченные» the list melted to
    one row during the run and the filter bar disappeared."""
    review, editor, session, flow = open_review(tmp_path)
    page = flow.run_queue.page
    for item in session.items:
        item.review_mark = "bad_generation"
    session.items[-1].review_mark = "bad_cutout"
    review.filter_mode = "marked"
    page.refresh_from_state()
    assert not review.results_bar.isHidden() and review.results_filter.isEnabled()
    assert sum(not page.queue.item(row).isHidden() for row in range(page.queue.count())) == len(session.items)
    session.running = True
    for item in session.items[:-1]:
        item.review_mark = "ok"  # what keep_version does when a picture is replaced
    page.refresh_from_state()
    assert not review.results_bar.isHidden()  # the menu stays on screen
    assert not review.results_filter.isEnabled()
    assert sum(not page.queue.item(row).isHidden() for row in range(page.queue.count())) == len(session.items)
    session.running = False
    page.refresh_from_state()
    assert review.results_filter.isEnabled()
    assert sum(not page.queue.item(row).isHidden() for row in range(page.queue.count())) == 1  # only the marked one
    editor.deleteLater()


def test_a_new_or_regenerated_picture_is_unchecked_until_the_owner_marks_it_ok(tmp_path):
    """Owner 2026-10-25: «Ок» must not be on every picture by default; regenerated ones must be looked at again."""
    from studio_clipart_review_ui import annotation, mark_state, visible
    review, editor, session, flow = open_review(tmp_path)
    item = session.items[0]
    assert item.review_mark == "ok" and not item.review_checked and mark_state(item) == "unchecked"
    assert annotation(item)[1] == "Не проверено" and visible(item, "unchecked") and not visible(item, "marked")
    review.strip.mark_buttons["ok"].click()
    assert item.review_checked and mark_state(item) == "ok" and not visible(item, "unchecked")
    assert annotation(item)[1] == "Ок"
    keep_version(item, session.output_dir, now=NOW)  # what regeneration does to the replaced picture
    assert item.review_mark == "ok" and not item.review_checked and mark_state(item) == "unchecked"
    editor.deleteLater()


def test_checked_flag_is_saved_and_restored_and_validated():
    from types import SimpleNamespace
    from studio_clipart_versions import restore_review, review_fields, validate_review_row
    item = SimpleNamespace(review_mark="ok", review_checked=True, review_note="", versions=[])
    row = review_fields(item)
    assert row == {"review_checked": True}
    validate_review_row(row)
    restored = SimpleNamespace(review_mark="x", review_checked=False, review_note="x", versions=[])
    restore_review(restored, row)
    assert restored.review_checked is True and restored.review_mark == "ok"
    restore_review(restored, {})  # an older project: nothing was ever confirmed
    assert restored.review_checked is False
    import pytest
    with pytest.raises(ValueError):
        validate_review_row({"review_checked": "yes"})


def test_clicks_share_one_delayed_save_and_close_flushes_it(tmp_path):
    review, editor, session, flow = open_review(tmp_path)
    strip = review.strip
    for mark in ("bad_cutout", "ok", "bad_generation", "ok"):
        strip.mark_buttons[mark].click()
    assert flow.saved == 0  # nothing was written while the owner clicks
    assert session.items[0].review_mark == "ok"  # the mark itself is in memory at once
    review.flush_save()
    assert flow.saved == 1
    review.flush_save()
    assert flow.saved == 1  # nothing pending: no second write
    strip.mark_buttons["bad_cutout"].click()
    review.detach_editor()  # closing the window flushes
    assert flow.saved == 2
    editor.deleteLater()


def _unsaved_dialog(answer):
    from PyQt6.QtWidgets import QMessageBox
    from types import SimpleNamespace
    from studio_auto_clipart_flow import _TransparencyDialog
    state = SimpleNamespace(dirty=True, saved=0, discarded=0, asked=0)

    def save():
        state.saved += 1
        state.dirty = False

    def discard():
        state.discarded += 1
        state.dirty = False

    editor = SimpleNamespace(_has_unsaved_changes=lambda: state.dirty, _save_clicked=save, discard_unsaved=discard)
    dialog = _TransparencyDialog()
    dialog.editor = editor

    def ask():
        state.asked += 1
        return getattr(QMessageBox.StandardButton, answer)

    dialog.ask_unsaved = ask
    dialog.show()
    return dialog, state


def test_close_with_unsaved_edits_asks_and_save_closes_the_window(tmp_path):
    dialog, state = _unsaved_dialog("Save")
    dialog.reject()  # what Esc and the window cross do
    assert state.asked == 1 and state.saved == 1 and not dialog.isVisible()


def test_close_with_unsaved_edits_discard_drops_them_and_closes(tmp_path):
    dialog, state = _unsaved_dialog("Discard")
    dialog.reject()
    assert state.discarded == 1 and state.saved == 0 and not dialog.isVisible()


def test_close_with_unsaved_edits_cancel_keeps_the_window_and_the_edits(tmp_path):
    dialog, state = _unsaved_dialog("Cancel")
    dialog.reject()
    assert dialog.isVisible() and state.dirty and state.saved == 0 and state.discarded == 0
    dialog.close()


def test_failed_save_keeps_the_window_open(tmp_path):
    dialog, state = _unsaved_dialog("Save")
    dialog.editor._save_clicked = lambda: None  # still dirty afterwards
    dialog.reject()
    assert dialog.isVisible()
    dialog.editor._has_unsaved_changes = lambda: False
    dialog.reject()
    assert not dialog.isVisible()


def test_close_without_edits_does_not_ask(tmp_path):
    dialog, state = _unsaved_dialog("Cancel")
    state.dirty = False
    dialog.reject()
    assert state.asked == 0 and not dialog.isVisible()


def test_editor_zoom_100_button_edge_rows_and_middle_button_pan(tmp_path):
    from PyQt6.QtCore import QPointF, Qt
    from PyQt6.QtGui import QMouseEvent
    from PyQt6.QtWidgets import QToolButton
    from v3_transparency_preview import ClipartTransparencyEditorPage
    editor = ClipartTransparencyEditorPage()
    editor.set_files([png(tmp_path / "a_ready.png")], selected_index=0)
    texts = [button.text() for button in editor.findChildren(QToolButton)]
    assert "100%" in texts and "По размеру" in texts
    next(button for button in editor.findChildren(QToolButton) if button.text() == "100%").click()
    assert editor.zoom_buttons[100].isChecked()
    # the edge buttons sit in two rows with a line between them
    harder, shrink = editor.edge_buttons["harder"], editor.edge_buttons["shrink"]
    assert shrink.geometry().isValid() and harder.parentWidget() is shrink.parentWidget()
    canvas = editor.canvas
    fits = []
    canvas.fit_requested.connect(lambda: fits.append(True))
    press = QMouseEvent(QMouseEvent.Type.MouseButtonPress, QPointF(10, 10), Qt.MouseButton.MiddleButton,
                        Qt.MouseButton.MiddleButton, Qt.KeyboardModifier.NoModifier)
    release = QMouseEvent(QMouseEvent.Type.MouseButtonRelease, QPointF(10, 10), Qt.MouseButton.MiddleButton,
                          Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier)
    canvas.mousePressEvent(press)
    assert canvas._panning  # the middle button pans without Space
    canvas.mouseReleaseEvent(release)
    assert not canvas._panning
    canvas.mouseDoubleClickEvent(QMouseEvent(QMouseEvent.Type.MouseButtonDblClick, QPointF(10, 10),
                                             Qt.MouseButton.MiddleButton, Qt.MouseButton.MiddleButton,
                                             Qt.KeyboardModifier.NoModifier))
    assert fits == [True]
    editor.deleteLater()



def test_editor_has_separate_size_and_preview_panels_without_the_file_counter(tmp_path):
    from PyQt6.QtGui import QColor
    from v3_transparency_preview import ClipartTransparencyEditorPage
    editor = ClipartTransparencyEditorPage()
    paths = [png(tmp_path / f"p{index}_ready.png") for index in range(3)]
    editor.set_files(paths, selected_index=0)
    editor.show()
    docks = editor.panel_docks
    assert {"files", "tools", "size", "preview"} <= set(docks)
    # the brush diameter sits under «Кисть»; the «Размеры» panel is the zoom bar (owner 2026-10-27)
    tools = editor.tools_scroll.widget()
    assert tools.isAncestorOf(editor.diameter_slider) and tools.isAncestorOf(editor.brush_style_buttons[100])
    assert not editor.size_frame.isAncestorOf(editor.diameter_slider)
    assert editor.size_frame.isAncestorOf(editor.zoom_bar) and editor.size_frame.isAncestorOf(editor.zoom_menu_button)
    # the preview panel is independent of the files panel
    docks["files"].hide()
    docks["preview"].show()
    assert docks["preview"].isVisible() and docks["preview"].widget() is editor.file_strip
    docks["files"].show()
    assert docks["preview"].isVisible()
    docks["preview"].hide()
    assert not docks["preview"].isVisible() and docks["files"].isVisible()
    # no «N из M» counter and no arrows
    assert editor.file_counter_label.isHidden() and editor.prev_file_button.isHidden() and editor.next_file_button.isHidden()
    # marks appear as dots on the thumbnails
    plain = editor.file_strip.item(1).icon().pixmap(56, 56).toImage()
    editor.set_file_annotations([None, ("#a78bfa", "Брак вырезания", False, False), None])
    marked = editor.file_strip.item(1).icon().pixmap(56, 56).toImage()
    assert marked != plain
    assert QColor(marked.pixelColor(56 - 10, 9)).name() == "#a78bfa"
    assert "selected" in editor.file_strip.styleSheet()  # the current picture is lit
    editor.deleteLater()


def test_prompt_can_be_edited_from_the_png_check_for_a_generation_defect(tmp_path, monkeypatch):
    """Owner 2026-10-27: after the check there was no visible place to change the prompt of a picture to re-create."""
    import studio_clipart_review_ui as ui
    from PyQt6.QtWidgets import QDialog
    from studio_set_export_ui import SetExportDialog
    review, editor, session, flow = open_review(tmp_path)
    from types import SimpleNamespace
    flow.shell.state = SimpleNamespace(data=SimpleNamespace(prompts=[]))

    class FakePrompt:
        def __init__(self, parent, **kwargs):
            self.kwargs = kwargs
        def exec(self):
            return QDialog.DialogCode.Accepted
        def prompt(self):
            return "a goose, softer outline"
        def deleteLater(self):
            pass

    monkeypatch.setattr(ui, "PromptDialog", FakePrompt)
    paths = [Path(item.output_path) for item in session.items]
    review.mark_output(paths[0], "bad_generation")
    review.edit_prompt_for(paths[0], None)
    assert session.items[0].payload["prompt"] == "a goose, softer outline"
    assert session.items[1].payload["prompt"] == "object 1"
    # the PNG-check screen offers the button only for a picture marked as a generation defect
    from studio_alpha_qc import AlphaQcReport
    dialog = SetExportDialog(paths, quality_reports=[AlphaQcReport(str(path.resolve()), "ok", (), width=8, height=8) for path in paths])
    dialog.enable_marks({str(paths[0].resolve()): "bad_generation", str(paths[1].resolve()): "ok"})
    dialog._show_quality_review()
    dialog.quality_list.setCurrentRow(0)
    assert not dialog.quality_prompt_button.isHidden()
    asked = []
    dialog.prompt_requested.connect(asked.append)
    dialog.quality_prompt_button.click()
    assert asked == [str(paths[0].resolve())]
    dialog.quality_list.setCurrentRow(1)
    assert dialog.quality_prompt_button.isHidden()
    dialog.reject()
    editor.deleteLater()


def test_strip_marks_are_mutually_exclusive_for_every_pair(tmp_path):
    review, editor, session, flow = open_review(tmp_path)
    strip = review.strip
    for first in strip.mark_buttons:
        for second in strip.mark_buttons:
            strip.mark_buttons[first].click()
            strip.mark_buttons[second].click()
            lit = [key for key, button in strip.mark_buttons.items() if button.isChecked()]
            assert lit == [second]
            assert session.items[0].review_mark == second
    editor.deleteLater()


def test_mark_shows_in_the_results_list_and_reaches_listeners_before_the_delayed_save(tmp_path):
    review, editor, session, flow = open_review(tmp_path)
    queue = flow.run_queue.page.queue
    heard = []
    review.marks_listeners.append(lambda: heard.append(review.marks_by_path()))
    review.strip.mark_buttons["bad_cutout"].click()
    assert flow.saved == 0  # the project is not saved yet
    assert queue.item(0).text().endswith("Брак вырезания")
    assert heard and list(heard[-1].values())[0] == "bad_cutout"
    review.mark_output(session.items[1].output_path, "bad_generation")
    assert "Брак генерации" in queue.item(1).text()
    assert list(heard[-1].values())[1] == "bad_generation"
    editor.deleteLater()


def test_strip_thumbnails_load_in_the_background_and_keep_mark_dots(tmp_path):
    from PyQt6.QtCore import Qt
    from PyQt6.QtWidgets import QApplication
    from v3_transparency_preview import ClipartTransparencyEditorPage
    editor = ClipartTransparencyEditorPage()
    paths = [png(tmp_path / f"a{index}_ready.png") for index in range(3)]
    editor.set_files(paths, selected_index=0)
    assert editor.file_strip.count() == 3  # the strip is there at once, with placeholders
    editor.set_file_annotations([("#24cabb", "Ок", False, False), None, ("#f0c38a", "Брак", False, False)])
    placeholder = editor.file_strip.item(0).data(Qt.ItemDataRole.UserRole).pixmap(56, 56).toImage()
    editor._thumb_pool.waitForDone()
    QApplication.processEvents()
    loaded = editor.file_strip.item(0).data(Qt.ItemDataRole.UserRole).pixmap(56, 56).toImage()
    assert loaded != placeholder  # the real picture replaced the placeholder
    dotted = editor.file_strip.item(0).icon().pixmap(56, 56).toImage()
    assert dotted != loaded  # and the mark dot was drawn on it after it arrived
    assert editor.file_strip.item(1).icon().pixmap(56, 56).toImage() == \
        editor.file_strip.item(1).data(Qt.ItemDataRole.UserRole).pixmap(56, 56).toImage()


def test_old_thumbnails_are_dropped_when_the_file_list_changes(tmp_path):
    from PyQt6.QtWidgets import QApplication
    from v3_transparency_preview import ClipartTransparencyEditorPage
    editor = ClipartTransparencyEditorPage()
    first = [png(tmp_path / "a_ready.png")]
    second = [png(tmp_path / "b_ready.png")]
    editor.set_files(first, selected_index=0)
    editor.set_files(second, selected_index=0)
    editor._thumb_pool.waitForDone()
    QApplication.processEvents()
    assert editor.file_strip.count() == 1 and editor.file_strip.item(0).toolTip() == "b_ready.png"


def test_only_the_marked_button_is_drawn_lit_after_any_sequence_of_clicks(tmp_path):
    review, editor, session, flow = open_review(tmp_path)
    editor.resize(1200, 800)
    editor.show()
    QApplication.processEvents()
    strip = review.strip
    strip.show_state(None)
    QApplication.processEvents()
    plain = {key: button.grab().toImage() for key, button in strip.mark_buttons.items()}
    for sequence in (("ok", "bad_generation", "bad_cutout"), ("bad_cutout", "ok", "deleted", "bad_generation")):
        for chosen in sequence:
            strip.mark_buttons[chosen].click()
            QApplication.processEvents()
            for key, button in strip.mark_buttons.items():
                drawn = button.grab().toImage()
                if key == chosen:
                    assert drawn != plain[key]
                else:
                    assert drawn == plain[key], f"{key} is still drawn lit after {chosen} was chosen"
    editor.deleteLater()


def test_rating_strip_is_a_panel_in_the_panels_menu(tmp_path):
    from PyQt6.QtCore import QSettings
    from v3_transparency_preview import ClipartTransparencyEditorPage
    QSettings(*ClipartTransparencyEditorPage.PANEL_SETTINGS).clear()
    review, editor, session, flow = open_review(tmp_path)
    editor.show()
    QApplication.processEvents()
    dock = editor.panel_docks["rating"]
    assert dock.widget() is review.strip and dock.isVisible()
    assert "Оценка" in [action.text() for action in editor.panels_button.menu().actions()]
    dock.hide()
    assert not dock.isVisible()
    editor.reset_panels()
    assert dock.isVisible()
    assert dock.geometry().bottom() < editor.panel_docks["preview"].geometry().bottom()  # above the thumbnails
    editor.deleteLater()


ORIGINAL_WITH_KEY = ("A cute bear. Their open gaps show the same solid #00FF00 background as outside the subject. "
                     "Clean edges.")


def _prompt_dialog(prompt, answer):
    from studio_clipart_review_ui import PromptDialog
    dialog = PromptDialog(None, path="", title="t", note="", prompt=prompt, original=ORIGINAL_WITH_KEY)
    asked = []
    dialog.ask_background = lambda sentences: asked.append(list(sentences)) or answer
    return dialog, asked


def test_prompt_without_the_key_colour_phrase_asks_and_can_restore_it(tmp_path):
    dialog, asked = _prompt_dialog("A cute bear in a hat. Clean edges.", "add")
    dialog._save()
    assert asked and "#00FF00" in asked[0][0]
    assert "#00FF00" in dialog.prompt() and dialog.result() == dialog.DialogCode.Accepted


def test_prompt_can_be_saved_without_the_phrase_or_sent_back_to_editing(tmp_path):
    dialog, _ = _prompt_dialog("A cute bear in a hat.", "keep")
    dialog._save()
    assert "#00FF00" not in dialog.prompt() and dialog.result() == dialog.DialogCode.Accepted
    dialog, _ = _prompt_dialog("A cute bear in a hat.", "back")
    dialog._save()
    assert dialog.result() != dialog.DialogCode.Accepted


def test_prompt_that_keeps_the_phrase_or_never_had_one_does_not_ask(tmp_path):
    dialog, asked = _prompt_dialog(ORIGINAL_WITH_KEY + " More leaves.", "back")
    dialog._save()
    assert not asked and dialog.result() == dialog.DialogCode.Accepted
    from studio_clipart_review_ui import PromptDialog
    plain = PromptDialog(None, path="", title="t", note="", prompt="new", original="no colour here")
    plain.ask_background = lambda sentences: pytest.fail("must not ask")
    plain._save()
    assert plain.result() == plain.DialogCode.Accepted


def test_edited_prompt_flag_is_set_cleared_saved_and_shown(tmp_path, monkeypatch):
    import studio_clipart_review_ui as ui
    from PyQt6.QtWidgets import QDialog
    from studio_clipart_versions import restore_review, review_fields, validate_review_row
    from types import SimpleNamespace
    review, editor, session, flow = open_review(tmp_path)
    flow.shell.state = SimpleNamespace(data=SimpleNamespace(prompts=[]))
    answers = ["a goose, softer outline"]

    class FakePrompt:
        def __init__(self, parent, **kwargs):
            pass
        def exec(self):
            return QDialog.DialogCode.Accepted
        def prompt(self):
            return answers[0]
        def deleteLater(self):
            pass

    monkeypatch.setattr(ui, "PromptDialog", FakePrompt)
    path = Path(session.items[0].output_path)
    review.edit_prompt_for(path, None)
    item = session.items[0]
    assert item.prompt_edited and review.edited_paths() == {str(path.resolve())}
    assert "промпт исправлен" in flow.run_queue.page.queue.item(0).text()
    assert "промпт исправлен" in editor.file_list.item(0).text()
    fields = review_fields(item)
    assert fields["prompt_edited"] is True
    validate_review_row({"status": "succeeded", "output_path": "", "attempts": 1, **fields})
    with pytest.raises(ValueError):
        validate_review_row({"prompt_edited": "yes"})
    restored = SimpleNamespace()
    restore_review(restored, fields)
    assert restored.prompt_edited is True
    answers[0] = "object 0"  # back to the very first text
    review.edit_prompt_for(path, None)
    assert not item.prompt_edited and not review.edited_paths()
    assert "prompt_edited" not in review_fields(item)
    editor.deleteLater()


def test_edited_prompt_badge_is_drawn_on_the_png_check_and_the_preview_strip(tmp_path):
    from studio_alpha_qc import AlphaQcReport
    from studio_set_export_ui import SetExportDialog
    from v3_transparency_preview import ClipartTransparencyEditorPage
    paths = [png(tmp_path / f"b{index}_ready.png") for index in range(2)]
    marks = {str(path.resolve()): "ok" for path in paths}
    reports = [AlphaQcReport(str(path.resolve()), "ok", (), width=8, height=8) for path in paths]
    dialog = SetExportDialog(paths, quality_reports=reports)
    dialog.enable_marks(marks)
    dialog._show_quality_review()
    plain = dialog.quality_list.item(0).icon().pixmap(120, 120).toImage()
    dialog.enable_marks(marks, edited={str(paths[0].resolve())})
    assert dialog.quality_list.item(0).icon().pixmap(120, 120).toImage() != plain
    assert "промпт исправлен" in dialog.quality_list.item(0).toolTip()
    assert "промпт исправлен" not in dialog.quality_list.item(1).toolTip()
    dialog.reject()
    editor = ClipartTransparencyEditorPage()
    editor.set_files(paths, selected_index=0)
    editor._thumb_pool.waitForDone()
    QApplication.processEvents()
    editor.set_file_annotations([("#24cabb", "Ок", False, False), ("#24cabb", "Ок", False, False)])
    before = editor.file_strip.item(0).icon().pixmap(56, 56).toImage()
    editor.set_file_annotations([("#24cabb", "Ок", False, False, True), ("#24cabb", "Ок", False, False)])
    assert editor.file_strip.item(0).icon().pixmap(56, 56).toImage() != before
    assert editor.file_strip.item(1).icon().pixmap(56, 56).toImage() == \
        editor.file_strip.item(1).icon().pixmap(56, 56).toImage()
    # The «Файлы» list shows the pencil too (owner 2026-10-27: it was only on the thumbnails).
    assert editor.file_list.item(0).icon().pixmap(40, 12).width() > editor.file_list.item(1).icon().pixmap(40, 12).width()


GUIDED = ("A goose.\nReference image 1: use only for colors.\nReference image 2: use only for pose.\n"
          "Reference image 3: use only for mood.")


def test_dropping_a_reference_removes_its_guidance_line_and_renumbers_the_rest():
    from studio_clipart_review_ui import drop_reference_guidance
    result = drop_reference_guidance(GUIDED, 2)
    assert "use only for pose" not in result
    assert "Reference image 2: use only for mood." in result and "Reference image 3" not in result
    assert drop_reference_guidance("plain text", 1) == "plain text"


def test_prompt_dialog_replaces_and_removes_references_for_this_picture(tmp_path):
    from studio_clipart_review_ui import PromptDialog
    first, second, other = (png(tmp_path / name) for name in ("r1.png", "r2.png", "new.png"))
    dialog = PromptDialog(None, path="", title="t", note="", prompt=GUIDED, original=GUIDED,
                          references=[str(first), str(second)])
    dialog.choose_reference = lambda: str(other)
    dialog.replace_reference(0)
    assert dialog.references() == [str(other), str(second)]
    assert dialog.prompt() == GUIDED  # replacing keeps the guidance: the reference is used for the same purpose
    dialog.remove_reference(0)
    assert dialog.references() == [str(second)]
    assert "use only for colors" not in dialog.prompt() and "Reference image 1: use only for pose." in dialog.prompt()
    dialog.choose_reference = lambda: str(tmp_path / "missing.png")
    shown = []
    from PyQt6.QtWidgets import QMessageBox
    QMessageBox.warning = lambda *args, **kwargs: shown.append(args[2])
    dialog.replace_reference(0)
    assert shown and dialog.references() == [str(second)]  # a broken file is refused and nothing changes


def test_changed_references_reach_only_this_picture_and_its_request(tmp_path, monkeypatch):
    import studio_clipart_review_ui as ui
    from PyQt6.QtWidgets import QDialog
    from types import SimpleNamespace
    review, editor, session, flow = open_review(tmp_path)
    keep = png(tmp_path / "keep.png")
    swap = png(tmp_path / "swap.png")
    for item in session.items:
        item.payload["references"] = [str(keep)]
    entries = [SimpleNamespace(object_id=item.payload.get("object_id", ""), references=[str(keep)], prompt="p")
               for item in session.items]
    set_references = [{"path": str(keep), "roles": [], "notes": ""}]
    flow.shell.state = SimpleNamespace(data=SimpleNamespace(prompts=entries, references=set_references))

    class FakePrompt:
        def __init__(self, parent, **kwargs):
            self.start = list(kwargs["references"])
        def exec(self):
            return QDialog.DialogCode.Accepted
        def prompt(self):
            return "object 0"
        def references(self):
            return [str(swap)]
        def deleteLater(self):
            pass

    monkeypatch.setattr(ui, "PromptDialog", FakePrompt)
    review.edit_prompt_for(Path(session.items[0].output_path), None)
    assert session.items[0].payload["references"] == [str(swap)]
    assert session.items[1].payload["references"] == [str(keep)]  # the other picture is untouched
    assert set_references == [{"path": str(keep), "roles": [], "notes": ""}]  # so is the set
    request = session.preview_regenerate([0, 1])
    assert [entry["references"] for entry in request.generated_prompts] == [[str(swap)], [str(keep)]]
    editor.deleteLater()


def test_prompt_dialog_reset_brings_back_text_and_references(tmp_path):
    from studio_clipart_review_ui import PromptDialog
    first, second = png(tmp_path / "r1.png"), png(tmp_path / "r2.png")
    dialog = PromptDialog(None, path="", title="t", note="", prompt=GUIDED, original=GUIDED,
                          references=[str(first), str(second)])
    dialog.remove_reference(0)
    dialog.reset_to_original()
    assert dialog.references() == [str(first), str(second)] and dialog.prompt() == GUIDED


def test_png_check_regenerate_button_follows_the_prompt_button_and_starts_one_picture(tmp_path):
    from studio_alpha_qc import AlphaQcReport
    from studio_set_export_ui import SetExportDialog
    review, editor, session, flow = open_review(tmp_path)
    paths = [Path(item.output_path) for item in session.items]
    reports = [AlphaQcReport(str(path.resolve()), "ok", (), width=8, height=8) for path in paths]
    dialog = SetExportDialog(paths, quality_reports=reports)
    dialog.enable_marks({str(paths[0].resolve()): "bad_generation", str(paths[1].resolve()): "ok"})
    dialog._show_quality_review()
    dialog.quality_list.setCurrentRow(0)
    assert not dialog.quality_regenerate_button.isHidden() and not dialog.quality_prompt_button.isHidden()
    dialog.quality_list.setCurrentRow(1)
    assert dialog.quality_regenerate_button.isHidden()
    dialog.quality_list.setCurrentRow(0)
    asked = []
    dialog.regenerate_requested.connect(asked.append)
    dialog.quality_regenerate_button.click()
    assert asked == [str(paths[0].resolve())]
    dialog.reject()
    flow.is_busy = lambda: False
    flow.run_queue.regenerate_selected = Mock(return_value=object())
    assert review.regenerate_path(paths[1]) is not None
    flow.run_queue.regenerate_selected.assert_called_once_with([1])
    flow.run_queue.regenerate_selected.reset_mock()
    flow.is_busy = lambda: True  # a run is going: nothing starts
    assert review.regenerate_path(paths[1]) is None
    flow.run_queue.regenerate_selected.assert_not_called()
    assert review.regenerate_path(tmp_path / "unknown.png") is None
    editor.deleteLater()


def test_png_check_opens_on_the_regenerated_picture_with_cleared_mark(tmp_path):
    from PyQt6.QtCore import Qt
    from studio_alpha_qc import AlphaQcReport
    from studio_set_export_ui import SetExportDialog
    paths = [png(tmp_path / "g1.png"), png(tmp_path / "g2.png")]
    reports = [AlphaQcReport(str(path.resolve()), "ok", (), width=8, height=8) for path in paths]
    dialog = SetExportDialog(paths, quality_reports=reports)
    dialog.enable_marks({str(paths[0].resolve()): "bad_generation", str(paths[1].resolve()): "bad_cutout"})
    dialog._viewed_quality.add(str(paths[1].resolve()))
    # The regenerated picture lost its mark (kept as a version); the panel is rebuilt with it cleared.
    dialog.enable_marks({str(paths[0].resolve()): "bad_generation", str(paths[1].resolve()): "ok"})
    dialog.focus_quality_path(paths[1])
    assert dialog.quality_list.currentItem().data(Qt.ItemDataRole.UserRole) == str(paths[1].resolve())
    assert not dialog.quality_marks_row.isHidden() or dialog.quality_mark_buttons["ok"].isChecked()
    assert dialog.quality_regenerate_button.isHidden()
    dialog.reject()


def test_png_check_cutout_button_is_only_for_cutout_defects_and_starts_one_picture(tmp_path):
    from studio_alpha_qc import AlphaQcReport
    from studio_set_export_ui import SetExportDialog
    review, editor, session, flow = open_review(tmp_path)
    paths = [Path(item.output_path) for item in session.items]
    reports = [AlphaQcReport(str(path.resolve()), "ok", (), width=8, height=8) for path in paths]
    dialog = SetExportDialog(paths, quality_reports=reports)
    dialog.enable_marks({str(paths[0].resolve()): "bad_cutout", str(paths[1].resolve()): "bad_generation"})
    dialog._show_quality_review()
    dialog.quality_list.setCurrentRow(0)
    assert not dialog.quality_cutout_button.isHidden() and dialog.quality_regenerate_button.isHidden()
    dialog.quality_list.setCurrentRow(1)
    assert dialog.quality_cutout_button.isHidden()
    dialog.quality_list.setCurrentRow(0)
    asked = []
    dialog.cutout_requested.connect(asked.append)
    dialog.quality_cutout_button.click()
    assert asked == [str(paths[0].resolve())]
    dialog.reject()
    flow.is_busy = lambda: False
    flow.run_queue.reprocess_selected = Mock(return_value=object())
    assert review.cutout_path(paths[1]) is not None
    flow.run_queue.reprocess_selected.assert_called_once()
    assert flow.run_queue.reprocess_selected.call_args.args[0] == [1]
    assert review.cutout_path(tmp_path / "unknown.png") is None
    editor.deleteLater()


def test_size_and_rating_panels_keep_minimal_height(tmp_path):
    review, editor, _session, _flow = open_review(tmp_path)
    editor.resize(1400, 1000)
    editor.show()
    QApplication.processEvents()
    for key in ("size", "rating"):
        dock = editor.panel_docks[key]
        content = dock.widget()
        assert content.sizePolicy().verticalPolicy() == QSizePolicy.Policy.Fixed
        assert dock.height() <= content.sizeHint().height() + dock.titleBarWidget().sizeHint().height() + 12
    editor.close()


def test_upscale_redo_starts_from_the_picture_before_the_stage(tmp_path):
    """Владелец 2026-10-30: «Апскейл заново» повторяет апскейл из сохранённой картинки до него.

    Генерация и удаление фона не запускаются: сохранённый вход уже несёт матте, поэтому конвейеру
    велено переиспользовать его (skip_remover_for_alpha), а не вырезать заново.
    """
    session = generation_session(tmp_path)
    cutout = png(Path(session.transient_dir) / "gen_upscale_input_000.png")
    session.items[0].cutout_path = str(cutout)
    controller = Mock()
    controller.is_busy.return_value = False
    controller.worker = None
    support = RunQueueSupport.__new__(RunQueueSupport)
    support.controller = controller
    support.session = session
    started = []
    support._start_worker = lambda _worker, request: started.append(request) or request

    support.upscale_redo_selected([0])

    assert started, "повтор апскейла не запустился"
    request = started[0]
    assert request.mode == "mode2_process"
    assert request.generated_prompts == []                      # никакой генерации
    assert request.selected_files == [str(cutout.resolve())]     # вход — картинка до апскейла
    assert request.settings["skip_remover_for_alpha"] is True    # вырезание не повторяем
    assert request.settings["overwrite_existing"] is True        # прежняя картинка станет версией
    controller.before_replace_outputs.assert_called_once_with([0], "upscale_redo")
    assert session.items[0].status is RunItemStatus.PENDING
    assert session.items[0].stage_statuses == {"generation": "complete", "background_removal": "complete"}

    # Картинка без сохранённого входа не берётся: запускать нечего.
    session.running = False
    session.items[1].cutout_path = ""
    controller.reset_mock()
    started.clear()
    assert support.session.upscale_redoable_indices([1]) == []
    support.upscale_redo_selected([1])
    assert started == [] and not controller.before_replace_outputs.called




def test_upscale_redo_explains_the_way_out_when_the_input_is_gone(tmp_path):
    """Владелец 2026-10-30: нет картинки до апскейла — сказать честно и предложить перегенерировать или вырезать заново."""
    review, editor, session, flow = open_review(tmp_path)
    path = session.items[0].output_path
    reason = review.upscale_redo_unavailable_reason(path)
    assert "картинка до апскейла" in reason
    assert "Перегенерируйте" in reason and "удалите фон заново" in reason
    assert "не найдена в проекте" in review.upscale_redo_unavailable_reason(tmp_path / "unknown.png").lower()
    editor.deleteLater()


def test_upscale_redo_uses_the_saved_input_for_one_picture(tmp_path):
    """Кнопка «Апскейл заново» у картинки запускает повтор этапа с сохранённой картинкой до него."""
    review, editor, session, flow = open_review(tmp_path)
    path = session.items[1].output_path
    session.items[1].cutout_path = str(png(Path(session.transient_dir) / "gen_upscale_input_001.png"))
    assert review.upscale_redo_unavailable_reason(path) == ""
    flow.run_queue.upscale_redo_selected = Mock(return_value=object())
    assert review.upscale_redo_path(path) is not None
    flow.run_queue.upscale_redo_selected.assert_called_once_with([1])
    editor.deleteLater()


def test_redo_menu_has_three_variants_with_the_full_path_in_the_tip(tmp_path):
    """Владелец 2026-10-30: короткие подписи, полный путь — в подсказке; третий пункт — «Апскейл заново»."""
    review, editor, session, flow = open_review(tmp_path)
    assert review.redo_generate_action.text() == "Перегенерировать"
    assert review.redo_cutout_action.text() == "Удалить фон заново"
    assert review.redo_upscale_action.text() == "Апскейл заново"
    assert "весь путь обработки" in review.redo_generate_action.toolTip()
    assert "апскейл → очистка края" in review.redo_cutout_action.toolTip()
    assert "Повторный апскейл вырезанной картинки" in review.redo_upscale_action.toolTip()
    assert "цена" not in review.redo_generate_action.toolTip().lower()
    assert "платно" not in review.redo_cutout_action.toolTip().lower()
    # Кнопка у самой картинки на месте и не скрыта.
    assert review.strip.upscale_button.text() == "Апскейл заново"
    assert review.strip.upscale_button in review.strip.persistent_actions
    editor.deleteLater()


def stopped_redo_session(tmp_path):
    """Состояние владельца 2026-10-30 (живая приёмка, экран «Результаты»).

    Повтор апскейла начался и был остановлен через секунду: все строки списка «отменены»
    (баннер «Обработано: 0 Ошибки: 0 Пропущено: 30 Всего: 30»), но сохранённая картинка
    до апскейла осталась на диске у каждой строки.
    """
    session = generation_session(tmp_path)
    for index, item in enumerate(session.items):
        item.cutout_path = str(png(Path(session.transient_dir) / f"gen_upscale_input_{index:03d}.png"))
    session.prepare_upscale_redo(list(range(len(session.items))))
    session.handle_cancelled_terminal()
    assert session.counts()["cancelled"] == len(session.items)
    return session


def test_a_cancelled_picture_with_a_saved_input_can_be_upscaled_again(tmp_path):
    """После остановки повтора строки «отменены», но вход апскейла сохранён: «Апскейл заново»
    берёт его так же, как у успешных и ошибочных картинок (владелец 2026-10-30)."""
    session = stopped_redo_session(tmp_path)
    inputs = [item.cutout_path for item in session.items]
    assert session.items[1].status is RunItemStatus.CANCELLED
    controller = Mock()
    controller.is_busy.return_value = False
    controller.worker = None
    support = RunQueueSupport.__new__(RunQueueSupport)
    support.controller = controller
    support.session = session
    started = []
    support._start_worker = lambda _worker, request: started.append(request) or request

    support.upscale_redo_selected([1])

    assert started, "сохранённый вход отменённой картинки не взят в повторный апскейл"
    request = started[0]
    assert request.mode == "mode2_process" and request.generated_prompts == []
    assert request.selected_files == [str(Path(inputs[1]).resolve())]
    assert session.items[1].status is RunItemStatus.PENDING
    assert session.items[1].short_message == "Ожидает повторного апскейла."
    controller.before_replace_outputs.assert_called_once_with([1], "upscale_redo")


def test_upscale_redo_on_selected_rows_after_a_stopped_redo_runs_from_the_saved_inputs(tmp_path, monkeypatch):
    """Живая приёмка 2026-10-30: строки выделены («Пропущено: 30» после остановки), нажатие
    «Апскейл заново» в меню «Переделать выбранные» запускает повтор именно для выделенной
    картинки, а не отвечает «Выделите картинки в списке»."""
    review, editor, session, flow = open_review(tmp_path)
    for index, item in enumerate(session.items):
        item.cutout_path = str(png(Path(session.transient_dir) / f"gen_upscale_input_{index:03d}.png"))
    session.prepare_upscale_redo([0, 1])
    session.handle_cancelled_terminal()
    assert session.counts()["cancelled"] == 2
    page = flow.run_queue.page
    page.queue.clearSelection()
    page.queue.item(1).setSelected(True)
    assert page.queue.selected_rows() == [1]  # строки выделены (и «Переделать выбранные» активна)
    dialogs = []
    monkeypatch.setattr(QMessageBox, "information",
                        lambda *args: dialogs.append(str(args[2])) or QMessageBox.StandardButton.Ok)
    monkeypatch.setattr(QMessageBox, "question",
                        lambda *args, **kwargs: QMessageBox.StandardButton.Yes)
    flow.run_queue.upscale_redo_selected = Mock(return_value=object())

    review.upscale_redo_selected_rows()

    flow.run_queue.upscale_redo_selected.assert_called_once_with([1])
    assert dialogs == [], "владелец получает «Выделите…» при выделенных строках"
    editor.deleteLater()


def test_selected_rows_without_a_saved_input_get_an_honest_upscale_redo_refusal(tmp_path, monkeypatch):
    """Выделенные строки без сохранённого входа: отказ называет причину (нет картинки до апскейла),
    не смешивая «нет входа» с «ничего не выделено» (владелец 2026-10-30)."""
    review, editor, session, flow = open_review(tmp_path)
    page = flow.run_queue.page
    session.items[0].status = RunItemStatus.CANCELLED  # незавершённая строка тоже без сохранённого входа
    for row in (0, 1):
        page.queue.item(row).setSelected(True)
    assert page.queue.selected_rows() == [0, 1]
    dialogs = []
    monkeypatch.setattr(QMessageBox, "information",
                        lambda *args: dialogs.append(str(args[2])) or QMessageBox.StandardButton.Ok)
    flow.run_queue.upscale_redo_selected = Mock(return_value=object())

    review.upscale_redo_selected_rows()

    flow.run_queue.upscale_redo_selected.assert_not_called()
    assert len(dialogs) == 1
    message = dialogs[0]
    assert "нет сохранённой картинки до апскейла" in message
    assert "Выделите" not in message, "при выделенных строках нельзя звать выделять их снова"
    assert "перегенерируйте" in message.lower() and "удалите фон заново" in message.lower()
    editor.deleteLater()


def test_empty_selection_still_asks_to_select_rows_for_upscale_redo(tmp_path, monkeypatch):
    """Пустое выделение: подсказка «Выделите картинки в списке» остаётся на месте."""
    review, editor, session, flow = open_review(tmp_path)
    page = flow.run_queue.page
    page.queue.clearSelection()
    dialogs = []
    monkeypatch.setattr(QMessageBox, "information",
                        lambda *args: dialogs.append(str(args[2])) or QMessageBox.StandardButton.Ok)
    flow.run_queue.upscale_redo_selected = Mock(return_value=object())

    review.upscale_redo_selected_rows()

    flow.run_queue.upscale_redo_selected.assert_not_called()
    assert len(dialogs) == 1 and "Выделите картинки в списке" in dialogs[0]
    editor.deleteLater()
