"""UI-to-worker DPI and actual editor-to-export regressions."""
from pathlib import Path
from types import SimpleNamespace
from zipfile import ZipFile

import pytest
from PIL import Image, ImageDraw
from PyQt6.QtWidgets import QApplication, QDialog, QLabel, QVBoxLayout, QWidget

from clipart_run_results import ClipartRunResultsExtension
from main import WorkerThread
from studio_alpha_qc import inspect_alpha_png
from studio_auto_clipart_flow import AutoClipartFlowController
from studio_set_export_ui import ExportWorker
from studio_working_files import digest, write_receipt
from v3_flow_runtime import FlowRunRequest
from v3_processing_flow import ProcessingRecipePage, build_processing_run_request
from v3_project_state import ProjectMode, ProjectState
from v3_run_queue import RunQueueSession, RunResultsPage
from v3_transparency_preview import ClipartTransparencyEditorPage


@pytest.fixture(scope="module", autouse=True)
def app():
    return QApplication.instance() or QApplication([])


def test_dpi_only_recipe_publishes_unchanged_pixels_at_300dpi(tmp_path):
    source = tmp_path / "input.png"
    image = Image.new("RGBA", (32, 32), (30, 50, 70, 100))
    image.save(source)
    original = source.read_bytes()
    state = ProjectState(mode=ProjectMode.PROCESSING)
    state.common.work_dir = str(tmp_path)
    state.processing.selected_files = [str(source)]
    page = ProcessingRecipePage(state, lambda: None)
    page.buttons["export_300_dpi"].click()
    request = build_processing_run_request(state, allow_full_image_changes=False,
                                          external_transfer_consent=False)
    errors = []
    worker = WorkerThread(**request.worker_kwargs())
    worker.error.connect(errors.append)
    worker.run()
    assert not errors
    outputs = list(Path(request.settings["output_dir"]).glob("*.png"))
    assert len(outputs) == 1
    with Image.open(outputs[0]) as saved:
        assert saved.info["dpi"] == pytest.approx((300, 300), abs=0.02)
        assert saved.convert("RGBA").tobytes() == image.tobytes()
    assert source.read_bytes() == original
    page.close()


def finished_page(root, image):
    output = root / "output" / "flower_ready.png"
    output.parent.mkdir(parents=True)
    image.save(output)
    state = ProjectState(mode=ProjectMode.CLIPART)
    request = FlowRunRequest("mode_both", str(root), {
        "output_dir": str(output.parent), "workspace_root": str(root),
    }, [{"prompt": "flower", "references": [], "result_kind": "clipart"}])
    session = RunQueueSession(request, ProjectMode.CLIPART)
    session.handle_item_progress(dict(item_index=1, total_items=1, stage="export",
                                     status="succeeded", output_path=str(output)))
    session.handle_finished()
    page = RunResultsPage(state, results_extension=ClipartRunResultsExtension())
    page.set_session(session)
    return state, session, page, output


def test_actual_editor_save_rechecks_blocked_and_accepted_export(tmp_path, monkeypatch):
    state, session, page, output = finished_page(tmp_path, Image.new("RGBA", (64, 64), "orange"))
    export_page = QWidget()
    QVBoxLayout(export_page)
    empty = QLabel("empty")
    export_page.layout().addWidget(empty)
    controller = SimpleNamespace(run_queue=SimpleNamespace(page=page, session=session), review=None,
        shell=SimpleNamespace(state=SimpleNamespace(data=state.clipart), refresh=lambda: None),
        export_panel=None, export_page=export_page, export_empty=empty)
    refresh = lambda: AutoClipartFlowController._refresh_export(controller)
    refresh()
    state.clipart.export_membership = controller.export_panel.saved_membership
    assert not controller.export_panel.export_button.isEnabled()

    def save_edit(dialog):
        editor = dialog.findChild(ClipartTransparencyEditorPage)
        mask = editor.document.mask
        # Make a valid transparent margin using the real modal editor/save path.
        ImageDraw.Draw(mask).rectangle((0, 0, 63, 63), fill=0)
        ImageDraw.Draw(mask).rectangle((12, 12, 51, 51), fill=255)
        editor.save_current()
        return QDialog.DialogCode.Accepted
    monkeypatch.setattr(QDialog, "exec", save_edit)
    AutoClipartFlowController._open_transparency_editor(controller, 0)
    refresh()
    assert inspect_alpha_png(output).status == "ok"
    assert controller.export_panel.quality_reports[str(output)].status == "ok"
    assert controller.export_panel.export_button.isEnabled()

    # A later in-place edit must also invalidate an old successful QC result.
    def erase_subject(dialog):
        editor = dialog.findChild(ClipartTransparencyEditorPage)
        ImageDraw.Draw(editor.document.mask).rectangle((0, 0, 63, 63), fill=0)
        editor.save_current()
        return QDialog.DialogCode.Accepted
    monkeypatch.setattr(QDialog, "exec", erase_subject)
    AutoClipartFlowController._open_transparency_editor(controller, 0)
    refresh()
    assert inspect_alpha_png(output).status == "block"
    assert controller.export_panel.quality_reports[str(output)].status == "block"
    assert not controller.export_panel.export_button.isEnabled()
    export_page.close()
    page.close()


def test_in_place_editor_save_updates_lineage_and_exports_selected_pixels(tmp_path):
    image = Image.new("RGBA", (64, 64))
    ImageDraw.Draw(image).ellipse((12, 12, 51, 51), fill="orange")
    state, session, page, output = finished_page(tmp_path, image)
    rough = tmp_path / "rough"
    rough.mkdir()
    original = rough / "rough_01_generated.png"
    Image.new("RGB", image.size, "blue").save(original)
    write_receipt(tmp_path, "fixture", [{"outputs": [{"path": str(output), "sha256": digest(output)}],
        "files": [{"name": original.name, "sha256": digest(original), "category": "generated"}]}])
    editor = ClipartTransparencyEditorPage()
    editor.set_files([output], rough_dir=rough)
    editor.copy_saved.connect(page.use_edited_output)
    editor.document.begin_stroke()
    editor.document.extend_stroke(((25, 25),), radius=2, action="remove", hardness=100)
    editor.document.end_stroke()
    editor.save_current()
    selected_bytes = output.read_bytes()
    worker = ExportWorker([{"title": "Set", "images": [output]}], tmp_path,
                          workspace=tmp_path, delete_originals=True)
    worker.run()
    assert not worker.error and len(worker.paths) == 1
    assert not original.exists()
    assert output.read_bytes() == selected_bytes
    with ZipFile(worker.paths[0]) as archive:
        pngs = [name for name in archive.namelist() if name.lower().endswith(".png")]
        assert len(pngs) == 1
        assert archive.read(pngs[0]) == selected_bytes
    editor.close()
    page.close()
