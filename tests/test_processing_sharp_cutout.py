"""Batch cutout through the same recipe, worker and results used by Processing."""
from io import BytesIO
from pathlib import Path
from unittest.mock import Mock

import pytest
from PIL import Image, ImageDraw
from PyQt6.QtWidgets import QApplication

import main
from v3_image_processing_ui import ProcessingPipelineEditor
from v3_processing_editor import apply_processing_recipe
from v3_processing_flow import build_processing_run_request
from v3_project_state import ProjectMode, ProjectState
from v3_run_queue import RunQueueSession, RunItemStatus, RunResultsPage


@pytest.fixture(scope='module')
def app():
    return QApplication.instance() or QApplication([])


def make_request(root, paths):
    state = ProjectState(mode=ProjectMode.PROCESSING)
    state.common.work_dir = str(root)
    state.processing.selected_files = [str(path) for path in paths]
    apply_processing_recipe(state, 'sharp_cutout')
    return state, build_processing_run_request(state, allow_full_image_changes=False,
                                               external_transfer_consent=False)


def test_recipe_survives_editor_and_saved_project(app, tmp_path):
    source = tmp_path / 'input.png'
    Image.new('RGB', (64, 64), 'white').save(source)
    state, request = make_request(tmp_path, [source])
    editor = ProcessingPipelineEditor(state.processing, lambda: None,
                                      title="Обработка", description="", include_cleanup=True)
    editor.refresh_from_state()
    # Editing an unrelated option must not replace U2Net or the hard mask mode.
    editor.operation_widgets['export_300_dpi'].setChecked(True)
    restored = ProjectState.from_dict(state.to_dict())
    ops = restored.processing.operations
    assert ops.local_rembg_model == 'u2net'
    assert ops.local_rembg_edge_quality == 'cutout'
    assert not ops.upscale_before and not ops.upscale_after
    assert not ops.trim and not ops.edge_shrink
    assert request.settings['remove_bg_provider'] == 'local_rembg'
    assert request.settings['local_rembg_edge_quality'] == 'cutout'
    editor.close()


def test_batch_keeps_sources_reuses_model_and_rejects_bad_mask(app, tmp_path, monkeypatch):
    sources = []
    for name, color in [('good', (180, 90, 50)), ('bad', (0, 0, 0))]:
        path = tmp_path / f'{name}.png'
        Image.new('RGB', (64, 64), color).save(path)
        sources.append(path)
    native = tmp_path / 'native.png'
    image = Image.new('RGBA', (64, 64))
    ImageDraw.Draw(image).rectangle((12, 12, 52, 52), fill=(10, 20, 30, 255))
    image.save(native)
    sources.append(native)
    original_bytes = {path: path.read_bytes() for path in sources}
    state, request = make_request(tmp_path, sources)
    session = RunQueueSession(request, ProjectMode.PROCESSING)
    def remove(data, session):
        with Image.open(BytesIO(data)) as source:
            result = source.convert('RGBA')
        if result.getpixel((0, 0))[0]:
            alpha = Image.new('L', result.size)
            ImageDraw.Draw(alpha).rectangle((8, 8, 55, 55), fill=230)
            result.putalpha(alpha)
        buffer = BytesIO()
        result.save(buffer, format='PNG')
        return buffer.getvalue()
    new_session = Mock(return_value=object())
    remover = Mock(side_effect=remove)
    monkeypatch.setattr(main, 'import_rembg_tools', lambda: (new_session, remover))
    worker = main.WorkerThread(request.mode, request.work_dir, request.settings,
                               selected_files=request.selected_files)
    worker.progress.connect(session.handle_progress)
    worker.item_progress.connect(session.handle_item_progress)
    worker._mode2_process_files(emit_final=False)
    session.handle_finished()
    assert [item.status for item in session.items] == [
        RunItemStatus.SUCCEEDED, RunItemStatus.FAILED, RunItemStatus.SUCCEEDED]
    new_session.assert_called_once_with('u2net')
    assert remover.call_count == 2  # Already transparent images retain their alpha.
    with Image.open(session.items[0].output_path) as output:
        assert output.size == (64, 64)
        assert {value for value, count in enumerate(output.getchannel('A').histogram()) if count} == {0, 255}
        assert output.getpixel((32, 32)) == (180, 90, 50, 255)
        assert output.getpixel((8, 32))[3] == 0
    with Image.open(session.items[2].output_path) as output:
        assert output.convert('RGBA').tobytes() == image.tobytes()
    assert all(path.read_bytes() == data for path, data in original_bytes.items())
    # The owner pressed «Ок» on both cut-outs: only confirmed pictures join export sets (SET-0, 2026-10-28).
    for item in session.items:
        if item.status is RunItemStatus.SUCCEEDED:
            item.review_mark, item.review_checked = 'ok', True
    page = RunResultsPage(state)
    page.set_session(session)
    assert len(page._export_paths()) == 2
    page.close()


def test_empty_and_opaque_masks_are_not_published(app, tmp_path):
    worker = main.WorkerThread('mode2_process', str(tmp_path), {'local_rembg_edge_quality': 'cutout'})
    for alpha in (0, 255):
        with pytest.raises(ValueError, match='выделить объект'):
            worker._apply_local_rembg_edge_quality(Image.new('RGBA', (64, 64), (50, 60, 70, alpha)))


def test_processing_editor_saved_copy_replaces_result(app, tmp_path):
    from studio_workflow_host import WorkflowHost
    from v3_processing_flow import install_processing_flow
    from v3_wizard import AppShell
    source = tmp_path / 'source.png'
    Image.new('RGB', (64, 64), 'white').save(source)
    state, request = make_request(tmp_path, [source])
    shell = AppShell(state)
    controller = install_processing_flow(WorkflowHost(shell, 'processing', worker_factory=Mock()))
    session = RunQueueSession(request, ProjectMode.PROCESSING)
    output = session.output_dir / 'source_ready.png'
    output.parent.mkdir(parents=True, exist_ok=True)
    image = Image.new('RGBA', (64, 64))
    ImageDraw.Draw(image).ellipse((10, 10, 50, 50), fill=(80, 120, 160, 255))
    image.save(output)
    session.handle_item_progress(dict(item_index=1, total_items=1, stage='export',
                                     status='succeeded', output_path=str(output)))
    # The owner pressed «Ок»: only confirmed pictures join export sets (SET-0, 2026-10-28).
    session.items[0].review_mark, session.items[0].review_checked = 'ok', True
    session.handle_finished()
    controller.run_queue.session = session
    controller.run_queue.page.set_session(session)
    editor = controller._create_transparency_page()
    edited = tmp_path / 'corrected.png'
    image.save(edited)
    editor.copy_saved.emit(str(output), str(edited))
    assert controller.run_queue.page._export_paths() == [edited.resolve()]
    assert session.items[0].editor_output_path == str(edited.resolve())
    editor.close()
    shell.close()


def test_cancel_during_segmentation_does_not_publish(app, tmp_path, monkeypatch):
    source = tmp_path / 'source.png'
    output = tmp_path / 'result.png'
    Image.new('RGB', (64, 64), 'white').save(source)
    worker = main.WorkerThread('mode2_process', str(tmp_path),
        {'local_rembg_model': 'u2net', 'local_rembg_edge_quality': 'cutout'})
    def remove(*args, **kwargs):
        image = Image.new('RGBA', (64, 64))
        ImageDraw.Draw(image).rectangle((10, 10, 50, 50), fill=(80, 120, 160, 255))
        data = BytesIO()
        image.save(data, format='PNG')
        worker.stop()
        return data.getvalue()
    monkeypatch.setattr(main, 'import_rembg_tools', lambda: (lambda model: object(), remove))
    with pytest.raises(main.ProcessingCancelled):
        worker._run_local_rembg(str(source), str(output))
    assert not output.exists()
