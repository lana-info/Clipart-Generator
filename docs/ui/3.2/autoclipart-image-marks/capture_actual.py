"""Screens of the implemented review UI on dummy pictures, for comparison with the mockups.

Real widgets: ClipartTransparencyEditorPage + ImageReview, RunResultsPage. No worker,
no provider requests. Run: python docs/ui/3.2/autoclipart-image-marks/capture_actual.py
"""
import importlib.util
import os
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parents[3]))
spec = importlib.util.spec_from_file_location("mockups", HERE / "render_mockups.py")
mockups = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mockups)  # creates the QApplication and the dummy pictures

from PyQt6.QtWidgets import QDialog, QVBoxLayout  # noqa: E402

from studio_clipart_review_ui import ImageReview  # noqa: E402
from studio_clipart_versions import keep_version  # noqa: E402
from v3_clipart_flow import ClipartRunRequest  # noqa: E402
from v3_components import apply_v3_theme  # noqa: E402
from v3_project_state import CommonProjectData, ProjectMode, ProjectState  # noqa: E402
from v3_run_queue import RunItemStatus, RunQueueSession, RunResultsPage  # noqa: E402
from v3_transparency_preview import ClipartTransparencyEditorPage  # noqa: E402

OUT = HERE / "actual"
W, H = 1120, 780
KEYS = {"ok": "ok", "gen": "bad_generation", "cut": "bad_cutout", "del": "deleted"}


class Flow:
    def __init__(self, session, state):
        page = RunResultsPage(state)
        page.set_session(session)
        self.run_queue = SimpleNamespace(session=session, page=page,
                                         reprocess_selected=lambda *a, **k: None,
                                         regenerate_selected=lambda *a, **k: None)
        self.shell = SimpleNamespace(mark_dirty=lambda: None, state=state)

    def _save_run(self):
        pass

    def is_busy(self):
        return False


def build(folder):
    paths, fixed, good_goose = mockups.make_files(folder)
    output = Path(folder)
    request = ClipartRunRequest(
        mode="mode1_generate_only", work_dir=str(output.parent),
        settings={"output_dir": str(output)},
        generated_prompts=[{"prompt": f"object {index}", "references": [], "object_id": f"o{index}"}
                           for index in range(len(paths))])
    session = RunQueueSession(request, ProjectMode.CLIPART)
    for item, path, (_name, mark, note) in zip(session.items, paths, mockups.FILES):
        item.status = RunItemStatus.SUCCEEDED
        item.output_path = str(path)
        item.display_name = path.name
        item.review_mark, item.review_note = KEYS[mark], note
    session.running = False
    raw = session.transient_dir / "rough_basket.png"
    raw.parent.mkdir(parents=True, exist_ok=True)
    mockups.basket().save(raw)
    session.items[2].source_path = str(raw)
    state = ProjectState(mode=ProjectMode.CLIPART, common=CommonProjectData(work_dir=str(output.parent)))
    return session, state, paths, fixed


def editor_window(session, state, paths, selected):
    flow = Flow(session, state)
    review = ImageReview(flow)
    review.install_results_page()
    dialog = QDialog()
    apply_v3_theme(dialog)
    layout = QVBoxLayout(dialog)
    editor = ClipartTransparencyEditorPage()
    layout.addWidget(editor)
    editor.set_files(paths, selected_index=selected)
    review.attach_editor(editor, paths)
    return dialog, editor, review, flow


def save(widget, name):
    widget.resize(W, H)
    widget.show()
    for _ in range(4):
        mockups.app.processEvents()
    OUT.mkdir(exist_ok=True)
    widget.grab().save(str(OUT / name))
    widget.hide()


def main():
    with tempfile.TemporaryDirectory() as root:
        folder = Path(root) / "output"
        folder.mkdir()
        session, state, paths, fixed = build(folder)
        for selected, name in ((0, "01-editor-ok"), (1, "02-editor-bad-generation"),
                               (2, "04-editor-bad-cutout")):
            dialog, *_ = editor_window(session, state, paths, selected)
            save(dialog, f"{name}-1120x780.png")
        # Preview after a redo: the previous picture is a version, the new one is current.
        item = session.items[2]
        mark, note = item.review_mark, item.review_note
        keep_version(item, folder, "basket prompt")
        fixed.replace(item.output_path)
        dialog, editor, review, _ = editor_window(session, state, paths, 2)
        item.review_mark = "bad_cutout"
        review._preview_row = 2
        editor.reload_file(item.output_path)
        review.refresh_editor()
        save(dialog, "05-editor-cutout-preview-1120x780.png")
        item.source_path = ""
        review._preview_row = None
        review.refresh_editor()
        save(dialog, "06-editor-cutout-unavailable-1120x780.png")
        item.review_mark, item.review_note = mark, note
        review.filter_mode = "deleted"
        dialog, editor, review, flow = editor_window(session, state, paths, 4)
        review.filter_mode = "deleted"
        review.refresh_editor()
        save(dialog, "07-editor-deleted-1120x780.png")
        review.filter_mode = "all"
        flow.run_queue.page.refresh_from_state()
        apply_v3_theme(flow.run_queue.page)
        save(flow.run_queue.page, "09-results-marked-1120x780.png")


if __name__ == "__main__":
    main()
    os._exit(0)
