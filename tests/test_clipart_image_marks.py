"""Auto Clipart owner review: marks, notes, versions, trash and cut-out redo."""
import os
from datetime import datetime
from pathlib import Path
from unittest.mock import Mock

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PIL import Image
from PyQt6.QtWidgets import QApplication

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


def test_deleted_picture_is_excluded_from_export(tmp_path):
    state = ProjectState(mode=ProjectMode.CLIPART, common=CommonProjectData(work_dir=str(tmp_path)))
    page = RunResultsPage(state)
    session = generation_session(tmp_path)
    page.set_session(session)
    assert len(page._export_paths()) == 2
    session.items[1].review_mark = "deleted"
    assert page._export_paths() == [Path(session.items[0].output_path).resolve()]
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
    support._start_prepared = lambda request: started.append(request) or request
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
                                         regenerate_selected=Mock(return_value=None))
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
    assert strip.to_generation_button.isVisibleTo(strip) and not strip.try_button.isVisibleTo(strip)
    strip.to_generation_button.click()
    assert session.items[0].review_mark == "bad_generation"
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


def test_escape_keeps_the_transparency_window_open_while_edits_are_unsaved(tmp_path):
    from types import SimpleNamespace
    from studio_auto_clipart_flow import _TransparencyDialog
    shown = []
    editor = SimpleNamespace(_has_unsaved_changes=lambda: True, _show_contour_status=shown.append)
    dialog = _TransparencyDialog()
    dialog.editor = editor
    dialog.show()
    dialog.reject()  # what Esc and the window cross do
    assert dialog.isVisible() and shown
    editor._has_unsaved_changes = lambda: False
    dialog.reject()
    assert not dialog.isVisible()
