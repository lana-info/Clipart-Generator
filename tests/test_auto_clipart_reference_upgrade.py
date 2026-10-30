import os
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import Mock

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import pytest
from PIL import Image
from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtWidgets import QApplication, QMessageBox

from license_client import LicenseAuthorization, ModuleEntitlement
from studio_style_profiles import all_style_modifiers
from v3_clipart_flow import build_clipart_run_request
from v3_mode_selection import V3ApplicationView
from v3_project_state import StepId
from v3_run_queue import RunItemStatus


class Worker(QObject):
    progress = pyqtSignal(str)
    progress_value = pyqtSignal(int)
    item_progress = pyqtSignal(object)
    finished = pyqtSignal(str)
    error = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.running = False

    def start(self):
        self.running = True

    def stop(self):
        self.running = False

    def isRunning(self):
        return self.running


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    _app = QApplication.instance() or QApplication([])
    now = datetime.now(timezone.utc)
    authorization = LicenseAuthorization('fixture', 'clipart-generator', 'fixture',
        now, now + timedelta(hours=1), module_entitlements=(
            ModuleEntitlement('auto-clipart', now, now + timedelta(hours=1)),))
    gate = Mock(status_text='Test', verification_text='Test', current_authorization=authorization)
    gate.authorize_run.return_value = authorization
    workers = []

    def make_worker(**kwargs):
        worker = Worker()
        workers.append(worker)
        return worker

    factory = Mock(side_effect=make_worker)
    view = V3ApplicationView(draft_path=tmp_path / 'draft.json', license_gate=gate,
        worker_factory=factory, runtime_settings_provider=lambda: {'kie_api_key': 'fixture'})
    monkeypatch.setattr(QMessageBox, 'warning', lambda *args: pytest.fail(str(args[-1])))
    view._handle_module_action('auto-clipart', 'open')
    controller = view.shell.workflow_controller('auto-clipart')
    controller.save_timer.stop()
    controller.brief.directory.setText(str(tmp_path))
    controller.brief.theme.setText('Flowers')
    controller.brief.total.setValue(2)
    reference = tmp_path / 'reference.png'
    Image.new('RGB', (16, 16), 'red').save(reference)
    controller.brief.reference_editor.add_reference(str(reference))
    for _ in range(4):
        controller.navigate(1)
    for index, item in enumerate(controller.brief.object_editor.items):
        item['name'] = f'Flower {index}'
    controller.brief.object_editor.refresh()
    controller.navigate(1)
    assert view.project_state.current_step is StepId.REVIEW_RUN
    controller.upscale_provider.setCurrentIndex(controller.upscale_provider.findData('kie'))
    yield view, controller, factory, workers, reference
    current = view.shell.workflow_controller('auto-clipart')
    current.save_timer.stop()
    for worker in workers:
        worker.stop()
        worker.finished.emit('Done')
    if current.run_queue.session:
        current.run_queue.session.running = False
    view.close()
    view.deleteLater()


def legacy_prompts(controller):
    for prompt in controller.shell.state.data.prompts:
        prompt.references = []
        prompt.prompt = 'Manually revised flower prompt'
    return controller.shell.state.data.automatic['compiled']


def test_legacy_extra_modifiers_require_correction_before_new_plan(workspace):
    _, controller, factory, _, _ = workspace
    value = ', '.join(modifier.title for modifier in all_style_modifiers()[:3])
    controller.brief.mood.setCurrentText(value)
    with pytest.raises(ValueError):
        controller.brief.snapshot()
    assert controller.brief.mood.currentText() == value
    factory.assert_not_called()
    controller.brief.mood.setCurrentText('')


def test_legacy_compiled_references_restore_without_overwriting_manual_prompt(workspace):
    view, controller, factory, _, reference = workspace
    fingerprint = legacy_prompts(controller)
    controller.navigate(-1)
    controller.navigate(1)
    for prompt in view.project_state.clipart.prompts:
        assert prompt.references == [str(reference)]
        assert prompt.prompt == 'Manually revised flower prompt'
    assert view.project_state.clipart.automatic['compiled'] == fingerprint
    factory.assert_not_called()


def test_legacy_project_reopens_directly_at_launch_with_references(workspace):
    view, controller, factory, _, reference = workspace
    legacy_prompts(controller)
    assert view._save_draft()
    assert view.continue_saved_project(view._active_project_id)
    resumed = view.shell.workflow_controller('auto-clipart')
    resumed.save_timer.stop()
    assert view.project_state.current_step is StepId.REVIEW_RUN
    for prompt in view.project_state.clipart.prompts:
        assert prompt.references == [str(reference)]
        assert prompt.prompt == 'Manually revised flower prompt'
    factory.assert_not_called()


def test_removed_reference_after_legacy_reopen_cannot_be_sent(workspace):
    view, controller, factory, _, reference = workspace
    legacy_prompts(controller)
    assert view._save_draft()
    assert view.continue_saved_project(view._active_project_id)
    resumed = view.shell.workflow_controller('auto-clipart')
    resumed.save_timer.stop()
    resumed.brief.reference_editor.files.setCurrentRow(0)
    resumed.brief.reference_editor._remove()
    resumed.flush()
    resumed._refresh_launch()
    for prompt in view.project_state.clipart.prompts:
        assert not prompt.references
        assert prompt.prompt == 'Manually revised flower prompt'
    request = build_clipart_run_request(resumed.shell.state)
    assert all(not entry['references'] for entry in request.generated_prompts)
    assert reference.exists()
    factory.assert_not_called()


def test_references_step_has_no_skip_button_and_next_goes_on_without_references(workspace):
    view, controller, factory, _, reference = workspace
    controller._select_step(StepId.PROMPT_REVIEW)
    assert not hasattr(controller.brief, 'skip_references_button')
    controller.brief.reference_editor.disable_all()  # the owner can still switch the references off one by one
    controller.navigate(1)
    assert view.project_state.current_step is StepId.GENERATION
    assert reference.exists()
    assert controller.brief.reference_editor.active_generation_paths() == ()
    controller.navigate(1)
    controller.navigate(1)
    assert view.project_state.current_step is StepId.REVIEW_RUN
    request = build_clipart_run_request(controller.shell.state)
    assert all(not item['references'] for item in request.generated_prompts)
    factory.assert_not_called()


def test_launch_uses_selected_reference_model_and_current_quote(workspace, monkeypatch):
    from v3_clipart_flow import estimate_clipart_cost

    view, controller, factory, _, _ = workspace
    assert controller.launch_page.count() == 2
    assert [controller.launch_page.tabText(index) for index in range(2)] == ["Промпты", "Модель"]
    controller.generation_page.refresh_from_state()
    assert controller.generation_page.model_combo.isHidden()
    assert not controller.generation_page.variants_spin.isHidden()
    assert not controller.generation_page.reference_controls_container.isHidden()
    assert '2' in controller.generation_page.reference_model_label.text()

    models = controller.generation_page.reference_model_combo
    models.setCurrentIndex(models.findData('gpt-image-2'))
    gpt_cost = estimate_clipart_cost(controller.shell.state)
    models.setCurrentIndex(models.findData('nano-banana-2'))
    banana_cost = estimate_clipart_cost(controller.shell.state)
    assert banana_cost.generation_usd != gpt_cost.generation_usd

    quote = []
    def decline(*args):
        quote.append(args[2])
        return QMessageBox.StandardButton.No
    monkeypatch.setattr(QMessageBox, 'question', decline)
    controller.navigate(1)
    assert view.project_state.current_step is StepId.REVIEW_RUN
    assert len(quote) == 1
    assert 'nano-banana-2' in quote[0]
    assert f'ориентировочно ${banana_cost.estimated_usd:.3f}' in quote[0]
    factory.assert_not_called()


def failed_session(controller, tmp_path):
    session = controller.run_queue.start_new(build_clipart_run_request(controller.shell.state))
    session.items[0].status = RunItemStatus.SUCCEEDED
    session.items[0].output_path = str(tmp_path / 'success.png')
    Image.new('RGBA', (16, 16), (255, 0, 0, 128)).save(session.items[0].output_path)
    session.items[0].attempts = 1
    session.items[1].status = RunItemStatus.FAILED
    session.items[1].attempts = 1
    session.handle_finished()
    return session


def test_retry_cancellation_does_not_mutate_queue(workspace, tmp_path, monkeypatch):
    _, controller, factory, _, _ = workspace
    session = failed_session(controller, tmp_path)
    before = deepcopy(session.items)

    def decline(*args):
        assert session.items == before
        assert not session.running
        assert '1' in args[2]
        return QMessageBox.StandardButton.No

    monkeypatch.setattr(QMessageBox, 'question', decline)
    assert controller.run_queue.retry_failed() is None
    assert session.items == before
    assert not session.running
    factory.assert_not_called()


def test_retry_only_failed_subset_uses_approved_copy_and_preserves_success(workspace, tmp_path, monkeypatch):
    _, controller, factory, workers, reference = workspace
    session = failed_session(controller, tmp_path)
    success = deepcopy(session.items[0])

    def accept(*args):
        assert session.items[1].status is RunItemStatus.FAILED
        assert session.items[1].attempts == 1
        assert not session.running
        assert reference.name in args[2]
        return QMessageBox.StandardButton.Yes

    monkeypatch.setattr(QMessageBox, 'question', accept)
    retry = controller.run_queue.retry_failed()
    assert retry is not None
    assert len(retry.generated_prompts) == 1
    assert session.items[0] == success
    assert session.items[1].attempts == 2
    factory.assert_called_once()
    submitted = factory.call_args.kwargs['generated_prompts']
    assert len(submitted) == 1
    assert submitted[0]['object_id'] == session.items[1].payload['object_id']
    copied = Path(submitted[0]['references'][0])
    assert copied != reference
    assert copied.read_bytes() == reference.read_bytes()
    assert retry.generated_prompts[0]['references'] == [str(reference)]
    assert controller._reference_consent is None
    workers[0].stop()
    workers[0].finished.emit('Done')
    assert not copied.exists()
    assert reference.exists()


def test_reference_change_after_retry_consent_prevents_worker(workspace, tmp_path, monkeypatch):
    _, controller, factory, _, reference = workspace
    session = failed_session(controller, tmp_path)
    before = deepcopy(session.items)
    warnings = []
    monkeypatch.setattr(QMessageBox, 'warning', lambda *args: warnings.append(args[-1]))

    def tamper(*args):
        Image.new('RGB', (16, 16), 'blue').save(reference)
        return QMessageBox.StandardButton.Yes

    monkeypatch.setattr(QMessageBox, 'question', tamper)
    assert controller.run_queue.retry_failed() is None
    factory.assert_not_called()
    assert session.items == before
    assert not session.running
    assert warnings
    assert controller._reference_consent is None


def test_initial_reference_run_uses_core_completion_signal(workspace, monkeypatch):
    view, controller, factory, workers, reference = workspace
    monkeypatch.setattr(QMessageBox, 'question', lambda *args: QMessageBox.StandardButton.Yes)
    view.shell.go_next()
    factory.assert_called_once()
    assert controller.run_queue.session.running
    copied = Path(factory.call_args.kwargs['generated_prompts'][0]['references'][0])
    assert copied.read_bytes() == reference.read_bytes()
    workers[0].stop()
    workers[0].finished.emit('Done')
    assert not copied.exists()


def test_removing_references_during_confirmation_cannot_bypass_consent(workspace, monkeypatch):
    view, controller, factory, _, _ = workspace

    def remove_references(*args):
        for prompt in view.project_state.clipart.prompts:
            prompt.references = []
        return QMessageBox.StandardButton.Yes

    warned = Mock()
    monkeypatch.setattr(QMessageBox, 'question', remove_references)
    monkeypatch.setattr(QMessageBox, 'warning', warned)  # the launch is refused with a notice
    view.shell.go_next()
    warned.assert_called_once()
    factory.assert_not_called()
    assert controller.run_queue.session is None
    assert controller._reference_consent is None
