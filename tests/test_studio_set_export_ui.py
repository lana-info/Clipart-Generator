from pathlib import Path
from types import SimpleNamespace
from zipfile import ZipFile

import pytest
from PIL import Image
from PyQt6.QtCore import QEvent, QEventLoop, QTimer, Qt
from PyQt6.QtWidgets import QApplication, QFileDialog, QInputDialog, QLabel, QMessageBox

from studio_set_export import export_clipart_sets, ExportCancelled
from studio_set_export_ui import SetExportDialog
from clipart_run_results import ClipartRunResultsExtension
from v3_project_state import ProjectState, ProjectMode, PromptEntry, save_project_draft, load_project_draft
from v3_run_queue import RunResultsPage, RunItem, RunItemStatus


def _clipart_results_page(state):
    return RunResultsPage(
        state, results_extension=ClipartRunResultsExtension()
    )


@pytest.fixture
def images(tmp_path):
    app = QApplication.instance() or QApplication([])
    paths = []
    for n in range(3):
        path = tmp_path / f'item-{n}.png'
        Image.new('RGBA', (32, 32), (60, 80, 90, 128)).save(path)
        paths.append(path)
    yield paths
    app.processEvents()


def test_manual_matrix_changes_membership_without_confirmation_checkbox(images):
    membership = _membership_for_sets(images, ['Мини', 'Полный'])
    dialog = SetExportDialog(images, membership=membership)
    dialog._show_manual_editor()
    dialog.table.item(0, 1).setCheckState(Qt.CheckState.Unchecked)
    dialog._save_membership()
    groups = dialog.groups()
    assert [group['title'] for group in groups] == ['Полный']
    assert len(groups[0]['images']) == 3
    dialog.reject()


def test_create_rename_delete_and_recreate_sets_without_touching_png(images, monkeypatch):
    dialog = SetExportDialog(images)
    saved = []
    dialog.membership_saved.connect(saved.append)
    dialog._show_create_page()
    dialog.new_set_name.setText('Зимние персонажи')
    dialog.new_set_images.item(1).setCheckState(Qt.CheckState.Checked)
    dialog._create_set()
    assert [group['title'] for group in dialog.groups()] == ['Set 1', 'Зимние персонажи']
    set_id = next(link['set_id'] for link in dialog.saved_membership[str(images[0])]['memberships']
                  if link['title'] == 'Зимние персонажи')
    dialog._show_manual_editor(set_id)
    monkeypatch.setattr(QInputDialog, 'getText', lambda *args, **kwargs: ('Зимний набор', True))
    dialog._rename_current_set()
    assert [group['title'] for group in dialog.groups()] == ['Set 1', 'Зимний набор']
    assert any(link['set_id'] == set_id and link['title'] == 'Зимний набор'
               for link in dialog.saved_membership[str(images[0])]['memberships'])
    monkeypatch.setattr(QMessageBox, 'question',
                        lambda *args, **kwargs: QMessageBox.StandardButton.Yes)
    dialog._delete_set(set_id)
    assert [group['title'] for group in dialog.groups()] == ['Set 1']
    first_id = dialog._set_catalog()[0][0]
    dialog._delete_set(first_id)
    with pytest.raises(ValueError):
        dialog.groups()
    assert all(item['memberships'] == [] for item in dialog.saved_membership.values())
    assert all(path.is_file() for path in images)
    reopened = SetExportDialog(images, membership=saved[-1])
    assert reopened._set_catalog() == []
    reopened._show_create_page()
    reopened.new_set_name.setText('Новый набор')
    reopened._create_set()
    assert reopened.groups()[0]['title'] == 'Новый набор'
    dialog.reject()
    reopened.reject()


def test_summary_filename_hover_shows_preview(images):
    dialog = SetExportDialog(images)
    dialog.show()
    QApplication.processEvents()
    dialog.table.itemEntered.emit(dialog.table.item(0, 0))
    assert dialog.preview_popup.isVisible()
    QApplication.sendEvent(dialog.table.viewport(), QEvent(QEvent.Type.Leave))
    assert not dialog.preview_popup.isVisible()
    dialog.reject()


def test_empty_set_stays_editable_and_blocks_export(images):
    dialog = SetExportDialog(images)
    dialog._show_manual_editor()
    for row in range(dialog.table.rowCount()):
        dialog.table.item(row, 1).setCheckState(Qt.CheckState.Unchecked)
    dialog._save_membership()
    assert dialog.summary_counts.text() == '3 изображения · 1 набор'
    assert not dialog.export_button.isEnabled()
    dialog._show_manual_editor()
    dialog.table.item(0, 1).setCheckState(Qt.CheckState.Checked)
    dialog._save_membership()
    assert dialog.export_button.isEnabled()
    dialog.reject()


def test_renamed_set_title_is_used_for_zip_filename(images, tmp_path, monkeypatch):
    dialog = SetExportDialog(images)
    set_id = dialog._set_catalog()[0][0]
    dialog._show_manual_editor(set_id)
    monkeypatch.setattr(QInputDialog, 'getText',
                        lambda *args, **kwargs: ('Зимние персонажи', True))
    dialog._rename_current_set()
    archives = export_clipart_sets(dialog.groups(), tmp_path)
    assert len(archives) == 1
    assert archives[0].name == 'set-zimnie-personazhi.zip'
    dialog.reject()


def test_export_opens_folder_without_confirmation_gate(images, monkeypatch):
    dialog = SetExportDialog(images)
    calls = []
    monkeypatch.setattr(QFileDialog, 'getExistingDirectory', lambda *args: calls.append(args) or '')
    dialog._export()
    assert calls
    assert dialog.worker is None
    dialog.reject()


def test_real_background_export_two_archives(images, tmp_path, monkeypatch):
    membership = _membership_for_sets(images, ['Мини', 'Полный'])
    dialog = SetExportDialog(images, membership=membership)
    monkeypatch.setattr(QFileDialog, 'getExistingDirectory', lambda *args: str(tmp_path))
    dialog._export()
    worker = dialog.worker
    loop = QEventLoop()
    worker.finished.connect(loop.quit)
    QTimer.singleShot(5000, loop.quit)
    loop.exec()
    assert dialog.worker is None
    assert len(dialog.exported) == 2
    png_counts = []
    for archive in dialog.exported:
        with ZipFile(archive) as z:
            pngs = [name for name in z.namelist() if name.startswith('png/')]
            png_counts.append(len(pngs))
            assert z.read('overview.pdf').startswith(b'%PDF')
    assert png_counts == [1, 3]
    assert dialog.export_button.isEnabled()
    dialog.reject()


def test_cancel_before_publish_removes_staging(images, tmp_path):
    before = set(tmp_path.iterdir())
    calls = []
    def cancelled():
        calls.append(1)
        return len(calls) >= 4
    with pytest.raises(ExportCancelled):
        export_clipart_sets([dict(title='Test', images=images)], tmp_path, cancelled=cancelled)
    assert set(tmp_path.iterdir()) == before


def test_results_only_export_current_successes(images, tmp_path):
    page = _clipart_results_page(ProjectState(mode=ProjectMode.CLIPART))
    page.session = SimpleNamespace(running=False, output_dir=tmp_path, items=[
        RunItem(1, 'success', status=RunItemStatus.SUCCEEDED, output_path=str(images[0])),
        RunItem(2, 'failed', status=RunItemStatus.FAILED, output_path=str(images[1])),
        RunItem(3, 'duplicate', status=RunItemStatus.SUCCEEDED, output_path=str(images[0])),
    ])
    assert page._export_paths() == [images[0]]
    # Unrecorded PNGs in the directory never become set members automatically.
    page.session.running = True
    assert page._export_paths() == []
    page.close()


def test_export_hidden_outside_clipart(images):
    page = RunResultsPage(ProjectState(mode=ProjectMode.PROCESSING))
    assert page.export_sets_button.isHidden()
    page.close()


def test_membership_save_reopen_and_preserve_other_runs(images, tmp_path):
    state = ProjectState(mode=ProjectMode.CLIPART)
    state.clipart.export_membership = {'/older/result.png': {'title': 'Старый набор', 'included': True}}
    current = _membership_for_sets(images, ['Мини', 'Полный'])
    state.clipart.export_membership.update(current)
    page = _clipart_results_page(state)
    dialog = SetExportDialog(images, membership=state.clipart.export_membership)
    dialog.membership_saved.connect(page._save_export_membership)
    changed = []
    page.membership_changed.connect(lambda: changed.append(True))
    dialog._show_manual_editor()
    dialog.table.item(1, 1).setCheckState(Qt.CheckState.Unchecked)
    dialog._save_membership()
    assert changed == [True]
    assert '/older/result.png' in state.clipart.export_membership
    path = tmp_path / 'project.json'
    save_project_draft(state, path)
    restored = load_project_draft(path)
    reopened = SetExportDialog(images, membership=restored.clipart.export_membership)
    reopened._show_manual_editor()
    assert reopened.table.item(1, 1).checkState() == Qt.CheckState.Unchecked
    for widget in (dialog, reopened, page):
        widget.close()


def test_invalid_membership_cannot_overwrite_draft(images, tmp_path):
    from clipart_project_state import ClipartProjectStateExtension
    extensions = (ClipartProjectStateExtension(),)
    state = ProjectState()
    path = tmp_path / 'project.json'
    save_project_draft(state, path, extensions=extensions)
    before = path.read_bytes()
    state.clipart.export_membership = {'image.png': {'title': 'test', 'included': 'yes'}}
    with pytest.raises(ValueError):
        save_project_draft(state, path, extensions=extensions)
    assert path.read_bytes() == before


def test_many_memberships_edit_save_reopen_preserves_other_links(images, tmp_path):
    from studio_export_membership import validate_export_membership
    key = str(images[0].resolve())
    membership = validate_export_membership({key: {'title': 'Mini', 'included': True},
        '/older/missing.png': {'title': 'Old', 'included': False}})
    for title in ('Standard', 'Maxi', 'Bundle'):
        membership[key]['memberships'].extend(validate_export_membership(
            {key: {'title': title, 'included': True}})[key]['memberships'])
    state = ProjectState(mode=ProjectMode.CLIPART)
    state.clipart.export_membership = membership
    page = _clipart_results_page(state)
    dialog = SetExportDialog([images[0]], membership=membership)
    dialog.membership_saved.connect(page._save_export_membership)
    dialog._show_manual_editor()
    assert dialog.table.rowCount() == 1
    assert dialog.table.columnCount() == 5
    assert len(dialog.groups()) == 4
    dialog.table.item(0, 2).setCheckState(Qt.CheckState.Unchecked)
    dialog._save_membership()
    path = tmp_path / 'many.json'
    save_project_draft(state, path)
    restored = load_project_draft(path)
    reopened = SetExportDialog([images[0]], membership=restored.clipart.export_membership)
    reopened._show_manual_editor()
    assert [link['included'] for link in restored.clipart.export_membership[key]['memberships']] == [True, False, True, True]
    assert restored.clipart.export_membership['/older/missing.png'] == membership['/older/missing.png']
    assert [group['title'] for group in reopened.groups()] == ['Mini', 'Maxi', 'Bundle']
    assert state.clipart.export_membership[key]['asset_id'] == membership[key]['asset_id']
    for widget in (dialog, reopened, page):
        widget.close()


def test_four_set_memberships_do_not_multiply_paid_generation_or_processing(images):
    from v3_clipart_flow import fal_endpoint_quantities

    state = ProjectState(mode=ProjectMode.CLIPART)
    state.clipart.prompts = [PromptEntry(prompt='single commercial asset')]
    state.clipart.generation.model = 'fal-ai/flux/schnell'
    operations = state.clipart.operations
    operations.upscale_before = True
    operations.upscale_before_provider = 'fal'
    operations.fal_upscale_model = 'fal-ai/recraft/upscale/crisp'
    operations.remove_background = True
    operations.remove_background_provider = 'fal'
    operations.fal_remove_bg_model = 'fal-ai/birefnet/v2'
    expected_paid_calls = {
        'fal-ai/flux/schnell': 1,
        'fal-ai/recraft/upscale/crisp': 1,
        'fal-ai/birefnet/v2': 1,
    }
    assert fal_endpoint_quantities(state) == expected_paid_calls

    state.clipart.export_membership = _membership_for_sets(
        [images[0]], ['Мини', 'Стандарт', 'Макси', 'Полный']
    )
    links = state.clipart.export_membership[str(images[0].resolve())]['memberships']
    assert len(links) == 4
    assert fal_endpoint_quantities(state) == expected_paid_calls


def test_bundle_plan_seeds_four_memberships_without_duplicate_generation(images):
    from studio_bundle_planner import propose_bundle_plan
    from studio_clipart_objects import fill_recipe
    from studio_clipart_recipe import ClipartRecipe
    recipe = ClipartRecipe()
    recipe.select(30)
    recipe.objects = fill_recipe([], recipe.counts)
    recipe.bundle_plan = propose_bundle_plan(recipe.objects)
    state = ProjectState(mode=ProjectMode.CLIPART)
    state.clipart.recipe = recipe.to_dict()
    page = _clipart_results_page(state)
    root = images[0].parent
    object_id = recipe.bundle_plan['sets'][0]['item_ids'][0]
    page.session = SimpleNamespace(running=False, output_dir=root, items=[
        RunItem(1, 'one', status=RunItemStatus.SUCCEEDED, output_path=str(images[0]),
                payload={'object_id': object_id})
    ])
    page._seed_bundle_membership()
    links = state.clipart.export_membership[str(images[0].resolve())]['memberships']
    expected = [entry for entry in recipe.bundle_plan['sets'] if object_id in entry['item_ids']]
    assert [(link['set_id'], link['title']) for link in links] == [
        (entry['set_id'], entry['title']) for entry in expected]
    assert all(link['included'] for link in links)
    page.close()


def test_bundle_plan_does_not_overwrite_manual_membership_or_choose_ambiguous_variant(images):
    from studio_bundle_planner import propose_bundle_plan
    from studio_clipart_objects import fill_recipe
    from studio_clipart_recipe import ClipartRecipe
    from studio_export_membership import validate_export_membership
    recipe = ClipartRecipe()
    recipe.select(30)
    recipe.objects = fill_recipe([], recipe.counts)
    recipe.bundle_plan = propose_bundle_plan(recipe.objects)
    state = ProjectState(mode=ProjectMode.CLIPART)
    state.clipart.recipe = recipe.to_dict()
    existing = validate_export_membership({str(images[0].resolve()): {'title': 'Manual', 'included': False}})
    state.clipart.export_membership = existing
    page = _clipart_results_page(state)
    root = images[0].parent
    ids = recipe.bundle_plan['sets'][-1]['item_ids']
    page.session = SimpleNamespace(running=False, output_dir=root, items=[
        RunItem(1, 'manual', status=RunItemStatus.SUCCEEDED, output_path=str(images[0]), payload={'object_id': ids[0]}),
        RunItem(2, 'v1', status=RunItemStatus.SUCCEEDED, output_path=str(images[1]), payload={'object_id': ids[1]}),
        RunItem(3, 'v2', status=RunItemStatus.SUCCEEDED, output_path=str(images[2]), payload={'object_id': ids[1]}),
    ])
    page._seed_bundle_membership()
    assert state.clipart.export_membership[str(images[0].resolve())] == existing[str(images[0].resolve())]
    assert str(images[1].resolve()) not in state.clipart.export_membership
    assert str(images[2].resolve()) not in state.clipart.export_membership
    page.close()


def _membership_for_sets(images, titles):
    from studio_export_membership import validate_export_membership
    value = validate_export_membership({str(images[0].resolve()): {'title': titles[0], 'included': True}})
    key = str(images[0].resolve())
    for title in titles[1:]:
        value[key]['memberships'].extend(validate_export_membership(
            {key: {'title': title, 'included': True}})[key]['memberships'])
    for image in images[1:]:
        other = validate_export_membership({str(image.resolve()): {'title': titles[-1], 'included': True}})
        value.update(other)
    return value


def test_approved_export_summary_is_primary_and_plain_language(images):
    membership = _membership_for_sets(images, ['Мини', 'Стандарт', 'Макси', 'Полный', 'Персонажи', 'Декор'])
    dialog = SetExportDialog(images, membership=membership)
    assert dialog.summary_page.isVisible() or not dialog.isVisible()
    assert dialog.summary_counts.text() == '3 изображения · 6 наборов'
    assert dialog.table.rowCount() == 3 and dialog.table.columnCount() == 7
    assert dialog.export_button.text() == 'Создать ZIP-наборы'
    assert dialog.new_set_button.text() == '+ Добавить набор'
    assert not hasattr(dialog, 'cards_scroll')
    assert not hasattr(dialog, 'delivery_note')
    assert not hasattr(dialog, 'reviewed')
    assert not hasattr(dialog, 'close_button')
    assert dialog.stack.currentWidget() is dialog.summary_page
    dialog.close()


def test_manual_editor_is_matrix_and_return_label_fits(images):
    membership = _membership_for_sets(images, ['Мини', 'Стандарт', 'Макси', 'Полный'])
    dialog = SetExportDialog(images, membership=membership)
    dialog._show_manual_editor()
    assert dialog.manual_page.isVisible() or not dialog.isVisible()
    assert dialog.table.columnCount() == 5
    assert dialog.table.horizontalHeaderItem(0).text() == 'PNG'
    assert [dialog.table.horizontalHeaderItem(i).text() for i in range(1, 5)] == ['Мини', 'Стандарт', 'Макси', 'Полный']
    for column in range(1, dialog.table.columnCount()):
        assert dialog.table.horizontalHeaderItem(column).textAlignment() & Qt.AlignmentFlag.AlignHCenter
    assert dialog.manual_page is dialog.summary_page
    assert dialog.rename_set_button.text() == 'Переименовать набор'
    dialog.close()


def test_hover_preview_popup_uses_filename_cell_and_cursor_position(images):
    membership = _membership_for_sets(images, ['Мини', 'Полный'])
    dialog = SetExportDialog(images, membership=membership)
    dialog._show_manual_editor()
    item = dialog.table.item(0, 0)
    from PyQt6.QtCore import QPoint
    point = QPoint(240, 180)
    dialog._show_preview(item, point)
    assert dialog.preview_popup.isVisible()
    assert dialog.preview_popup.pixmap() is not None
    assert not dialog.preview_popup.pixmap().isNull()
    assert dialog.preview_popup.pos().x() >= point.x()
    assert dialog.preview_popup.pos().y() >= point.y()
    dialog._hide_preview()
    assert not dialog.preview_popup.isVisible()
    dialog.close()


def test_export_no_longer_requires_confirmation_checkbox(images, tmp_path, monkeypatch):
    membership = _membership_for_sets(images, ['Мини', 'Полный'])
    dialog = SetExportDialog(images, membership=membership)
    monkeypatch.setattr(QFileDialog, 'getExistingDirectory', lambda *args: str(tmp_path))
    dialog._export()
    worker = dialog.worker
    assert worker is not None
    loop = QEventLoop()
    worker.finished.connect(loop.quit)
    QTimer.singleShot(5000, loop.quit)
    loop.exec()
    assert dialog.worker is None
    assert len(dialog.exported) == 2
    dialog.close()


def test_bundle_export_issues_report_missing_and_ambiguous_results(images):
    from studio_bundle_planner import propose_bundle_plan
    from studio_clipart_objects import fill_recipe
    from studio_clipart_recipe import ClipartRecipe
    recipe = ClipartRecipe()
    recipe.select(8)
    recipe.objects = fill_recipe([], recipe.counts)
    recipe.bundle_plan = propose_bundle_plan(recipe.objects)
    state = ProjectState(mode=ProjectMode.CLIPART)
    state.clipart.recipe = recipe.to_dict()
    page = _clipart_results_page(state)
    root = images[0].parent
    ids = recipe.bundle_plan['sets'][-1]['item_ids']
    page.session = SimpleNamespace(running=False, output_dir=root, items=[
        RunItem(1, 'v1', status=RunItemStatus.SUCCEEDED, output_path=str(images[0]), payload={'object_id': ids[0]}),
        RunItem(2, 'v2', status=RunItemStatus.SUCCEEDED, output_path=str(images[1]), payload={'object_id': ids[0]}),
        RunItem(3, 'failed', status=RunItemStatus.FAILED, output_path='', payload={'object_id': ids[1]}),
    ])
    issues = page._bundle_export_issues()
    assert {issue['kind'] for issue in issues} == {'ambiguous', 'missing'}
    assert next(issue for issue in issues if issue['kind'] == 'ambiguous')['count'] == 2
    assert any(issue['object_id'] == ids[1] for issue in issues if issue['kind'] == 'missing')
    page.close()


def test_summary_warning_explains_action_and_blocks_export(images):
    membership = _membership_for_sets(images, ['Мини', 'Полный'])
    issues = [
        {'kind': 'ambiguous', 'object_id': 'a', 'count': 2},
        {'kind': 'missing', 'object_id': 'b', 'count': 0},
    ]
    dialog = SetExportDialog(images, membership=membership, review_issues=issues)
    assert dialog.issue_panel.isVisible() or not dialog.isVisible()
    assert 'Не завершено: 1' in dialog.issue_text.text()
    assert 'Нужно выбрать вариант: 1' in dialog.issue_text.text()
    assert dialog.review_now_button.text() == 'Проверить'
    assert not dialog.ready_only.isChecked()
    assert not dialog.export_button.isEnabled()
    dialog.review_now_button.click()
    assert dialog.stack.currentWidget() is dialog.manual_page
    dialog.close()


def test_bundle_export_issues_deduplicates_same_png_for_same_object(images):
    from studio_bundle_planner import propose_bundle_plan
    from studio_clipart_objects import fill_recipe
    from studio_clipart_recipe import ClipartRecipe
    recipe = ClipartRecipe()
    recipe.select(8)
    recipe.objects = fill_recipe([], recipe.counts)
    recipe.bundle_plan = propose_bundle_plan(recipe.objects)
    state = ProjectState(mode=ProjectMode.CLIPART)
    state.clipart.recipe = recipe.to_dict()
    page = _clipart_results_page(state)
    root = images[0].parent
    object_id = recipe.bundle_plan['sets'][-1]['item_ids'][0]
    page.session = SimpleNamespace(running=False, output_dir=root, items=[
        RunItem(1, 'v1', status=RunItemStatus.SUCCEEDED, output_path=str(images[0]), payload={'object_id': object_id}),
        RunItem(2, 'duplicate record', status=RunItemStatus.SUCCEEDED, output_path=str(images[0]), payload={'object_id': object_id}),
    ])
    issues = page._bundle_export_issues()
    assert not any(issue['object_id'] == object_id and issue['kind'] == 'ambiguous' for issue in issues)
    page.close()


def test_table_membership_is_saved_immediately_and_restores_on_reopen(images):
    membership = _membership_for_sets(images, ['Мини', 'Полный'])
    dialog = SetExportDialog(images, membership=membership)
    saved = []
    dialog.membership_saved.connect(saved.append)
    originals = [path.read_bytes() for path in images]
    dialog.table.item(0, 1).setCheckState(Qt.CheckState.Unchecked)
    assert saved
    key = str(images[0].resolve())
    assert dialog.saved_membership[key]['memberships'][0]['included'] is False
    assert [group['title'] for group in dialog.groups()] == ['Полный']
    reopened = SetExportDialog(images, membership=saved[-1])
    assert reopened.table.item(0, 1).checkState() == Qt.CheckState.Unchecked
    assert [path.read_bytes() for path in images] == originals
    dialog.close()
    reopened.close()


def test_reselecting_second_variant_restores_ambiguity_and_blocks_partial_export(images, monkeypatch):
    paths = [str(path.resolve()) for path in images[:2]]
    ambiguous = {'kind': 'ambiguous', 'object_id': 'a', 'count': 2, 'paths': paths}
    missing = {'kind': 'missing', 'object_id': 'b'}
    dialog = SetExportDialog(images[:2],
        membership=_membership_for_sets(images[:2], ['Full Bundle']),
        review_issues=[ambiguous, missing])
    dialog.ready_only.setChecked(True)
    assert not dialog.export_button.isEnabled()
    dialog.table.item(1, 1).setCheckState(Qt.CheckState.Unchecked)
    assert dialog.review_issues == [missing]
    assert dialog.export_button.isEnabled()
    dialog.table.item(1, 1).setCheckState(Qt.CheckState.Checked)
    assert dialog.review_issues == [ambiguous, missing]
    assert not dialog.export_button.isEnabled()
    monkeypatch.setattr(QFileDialog, 'getExistingDirectory',
        lambda *args: pytest.fail('Ambiguous variants must not start export'))
    dialog._export()
    dialog.table.item(0, 1).setCheckState(Qt.CheckState.Unchecked)
    assert dialog.review_issues == [missing]
    assert dialog.export_button.isEnabled()
    assert dialog.groups()[0]['images'] == [images[1].resolve()]
    dialog.table.item(1, 1).setCheckState(Qt.CheckState.Unchecked)
    assert dialog.review_issues == [ambiguous, missing]
    assert not dialog.export_button.isEnabled()
    dialog.reject()


def test_saved_manual_choice_resolves_ambiguous_issue_but_missing_stays_blocking(images):
    membership = _membership_for_sets(images, ['Мини', 'Полный'])
    ambiguous_paths = [str(images[0].resolve()), str(images[1].resolve())]
    issues = [
        {'kind': 'ambiguous', 'object_id': 'a', 'count': 2, 'paths': ambiguous_paths},
        {'kind': 'missing', 'object_id': 'b', 'count': 0, 'paths': []},
    ]
    dialog = SetExportDialog(images, membership=membership, review_issues=issues)
    dialog._show_manual_editor()
    # Exclude the second variant from every set; keep the first variant selected.
    for column in range(1, dialog.table.columnCount()):
        dialog.table.item(1, column).setCheckState(Qt.CheckState.Unchecked)
    dialog._save_membership()
    assert [issue['kind'] for issue in dialog.review_issues] == ['missing']
    assert not dialog.export_button.isEnabled()
    dialog.close()


def test_reopening_saved_variant_choice_resolves_then_rechecks_ambiguity(images):
    paths = [str(path.resolve()) for path in images[:2]]
    ambiguous = {'kind': 'ambiguous', 'object_id': 'a', 'count': 2, 'paths': paths}
    membership = _membership_for_sets(images[:2], ['Full Bundle'])
    membership[paths[1]]['memberships'][0]['included'] = False
    dialog = SetExportDialog(images[:2], membership=membership, review_issues=[ambiguous])
    assert dialog.review_issues == []
    assert dialog.export_button.isEnabled()
    dialog.table.item(1, 1).setCheckState(Qt.CheckState.Checked)
    assert dialog.review_issues == [ambiguous]
    assert not dialog.export_button.isEnabled()
    dialog.reject()


def test_bundle_membership_seed_deduplicates_duplicate_session_records(images):
    from studio_bundle_planner import propose_bundle_plan
    from studio_clipart_objects import fill_recipe
    from studio_clipart_recipe import ClipartRecipe
    recipe = ClipartRecipe()
    recipe.select(8)
    recipe.objects = fill_recipe([], recipe.counts)
    recipe.bundle_plan = propose_bundle_plan(recipe.objects)
    state = ProjectState(mode=ProjectMode.CLIPART)
    state.clipart.recipe = recipe.to_dict()
    page = _clipart_results_page(state)
    root = images[0].parent
    object_id = recipe.bundle_plan['sets'][-1]['item_ids'][0]
    page.session = SimpleNamespace(running=False, output_dir=root, items=[
        RunItem(1, 'v1', status=RunItemStatus.SUCCEEDED, output_path=str(images[0]), payload={'object_id': object_id}),
        RunItem(2, 'same file again', status=RunItemStatus.SUCCEEDED, output_path=str(images[0]), payload={'object_id': object_id}),
    ])
    assert page._seed_bundle_membership()
    key = str(images[0].resolve())
    assert key in state.clipart.export_membership
    assert state.clipart.export_membership[key]['memberships']
    page.close()


def test_quality_review_warning_explains_problem_without_blocking_export(images):
    from studio_alpha_qc import AlphaQcIssue, AlphaQcReport
    membership = _membership_for_sets([images[0]], ['Мини'])
    report = AlphaQcReport(
        str(images[0].resolve()), 'review',
        (AlphaQcIssue('touches_edge', 'review',
                      'Видимые пиксели доходят до края холста.',
                      'Проверьте края изображения.'),),
        width=32, height=32,
    )
    dialog = SetExportDialog([images[0]], membership=membership, quality_reports=[report])
    assert dialog.quality_panel.isVisible() or not dialog.isVisible()
    assert '1 нужно проверить' in dialog.quality_summary_label.text()
    dialog._refresh_quality_page()
    assert dialog.export_button.isEnabled()
    assert dialog.quality_export_button.isEnabled()
    dialog._show_quality_review()
    assert dialog.quality_list.count() == 1
    assert dialog.quality_list.item(0).text() == images[0].name  # no caption under the thumbnail
    assert 'доходят до края' in dialog.quality_picture.toolTip()
    assert dialog.quality_issue_text.isHidden() and dialog.quality_issue_title.isHidden()
    dialog.reject()


def test_quality_blocker_disables_export_until_explicit_exclusion_without_deleting_file(images):
    from studio_alpha_qc import AlphaQcIssue, AlphaQcReport
    membership = _membership_for_sets(images[:2], ['Мини'])
    blocked = AlphaQcReport(
        str(images[0].resolve()), 'block',
        (AlphaQcIssue('no_transparency', 'block',
                      'В PNG нет прозрачного фона.',
                      'Исправьте фон или исключите дизайн.'),),
        width=32, height=32,
    )
    dialog = SetExportDialog(images[:2], membership=membership, quality_reports=[blocked])
    saved = []
    dialog.membership_saved.connect(saved.append)
    assert not dialog.export_button.isEnabled()
    dialog._show_quality_review()
    assert not dialog.quality_export_button.isEnabled()
    dialog.quality_list.setCurrentRow(0)
    assert dialog.quality_exclude_button.isEnabled()
    dialog.quality_exclude_button.click()
    assert images[0].is_file()
    key = str(images[0].resolve())
    assert saved
    assert all(not link['included'] for link in saved[-1][key]['memberships'])
    assert dialog.export_button.isEnabled()
    assert dialog.quality_export_button.isEnabled()
    assert 'Исключено' in dialog.quality_list.item(0).toolTip()
    dialog.reject()


def test_quality_summary_clears_stale_blocker_text_after_exclusion(images):
    from studio_alpha_qc import AlphaQcIssue, AlphaQcReport
    membership = _membership_for_sets(images[:2], ['Мини'])
    blocked = AlphaQcReport(
        str(images[0].resolve()), 'block',
        (AlphaQcIssue('no_transparency', 'block', 'Нет прозрачности.',
                      'Исправьте или исключите.'),), width=32, height=32,
    )
    dialog = SetExportDialog(images[:2], membership=membership, quality_reports=[blocked])
    dialog._show_quality_review()
    dialog.quality_list.setCurrentRow(0)
    dialog.quality_exclude_button.click()
    assert not dialog._needs_attention(str(images[0].resolve()))  # nothing left to look at
    dialog.reject()


def test_quality_fix_action_emits_exact_png_path(images):
    from studio_alpha_qc import AlphaQcIssue, AlphaQcReport
    membership = _membership_for_sets([images[0]], ['Мини'])
    report = AlphaQcReport(
        str(images[0].resolve()), 'review',
        (AlphaQcIssue('color_fringe', 'review', 'Подозрительная цветная кайма.',
                      'Очистите края.'),), width=32, height=32,
    )
    dialog = SetExportDialog([images[0]], membership=membership, quality_reports=[report])
    requested = []
    dialog.fix_requested.connect(requested.append)
    dialog._show_quality_review()
    dialog.quality_list.setCurrentRow(0)
    dialog.quality_fix_button.click()
    assert requested == [str(images[0].resolve())]


def test_quality_exclusion_resolves_ambiguity_when_one_variant_remains(images):
    from studio_alpha_qc import AlphaQcIssue, AlphaQcReport
    membership = _membership_for_sets(images[:2], ['Мини'])
    paths = [str(image.resolve()) for image in images[:2]]
    issue = {'kind': 'ambiguous', 'object_id': 'obj-1', 'count': 2, 'paths': paths}
    blocked = AlphaQcReport(
        paths[0], 'block',
        (AlphaQcIssue('no_transparency', 'block', 'Нет прозрачности.',
                      'Исправьте или исключите.'),), width=32, height=32,
    )
    dialog = SetExportDialog(
        images[:2], membership=membership, review_issues=[issue], quality_reports=[blocked]
    )
    assert len(dialog.review_issues) == 1
    dialog._show_quality_review()
    dialog.quality_list.setCurrentRow(0)
    dialog.quality_exclude_button.click()
    assert dialog.review_issues == []
    assert dialog.export_button.isEnabled()
    dialog.reject()


def test_quality_controls_lock_while_export_worker_is_active(images, tmp_path, monkeypatch):
    from studio_alpha_qc import AlphaQcIssue, AlphaQcReport
    membership = _membership_for_sets(images[:1], ['Мини'])
    report = AlphaQcReport(
        str(images[0].resolve()), 'review',
        (AlphaQcIssue('touches_edge', 'review', 'Проверьте край.', 'Проверьте PNG.'),),
        width=32, height=32,
    )
    dialog = SetExportDialog(images[:1], membership=membership, quality_reports=[report])
    monkeypatch.setattr(QFileDialog, 'getExistingDirectory', lambda *args: str(tmp_path))
    monkeypatch.setattr('studio_set_export_ui.ExportWorker.start', lambda self: None)
    dialog._show_quality_review()
    dialog._export()
    assert dialog.worker is not None
    assert not dialog.quality_export_button.isEnabled()
    assert not dialog.quality_back_button.isEnabled()
    assert not dialog.quality_fix_button.isEnabled()
    assert not dialog.quality_exclude_button.isEnabled()
    dialog._quality_selected(0)
    assert not dialog.quality_fix_button.isEnabled()
    assert not dialog.quality_exclude_button.isEnabled()
    dialog.worker.deleteLater()
    dialog.worker = None
    dialog.reject()


def test_partial_export_needs_explicit_choice_and_preserves_missing_issues(images, tmp_path, monkeypatch):
    issues = [{'kind': 'missing', 'object_id': str(n), 'count': 0, 'paths': []} for n in range(19)]
    dialog = SetExportDialog(images[:1], review_issues=issues)
    assert dialog.table.rowCount() == 1
    assert not dialog.ready_only.isChecked()
    assert not dialog.export_button.isEnabled()
    assert 'Не завершено: 19' in dialog.issue_text.text()
    originals = images[0].read_bytes()
    dialog.ready_only.setChecked(True)
    assert dialog.export_button.isEnabled()
    assert dialog.review_issues == issues
    monkeypatch.setattr(QFileDialog, 'getExistingDirectory', lambda *args: str(tmp_path / 'archives'))
    (tmp_path / 'archives').mkdir()
    dialog._export()
    worker = dialog.worker
    assert worker is not None
    assert not dialog.table.isEnabled() and not dialog.ready_only.isEnabled()
    loop = QEventLoop()
    worker.finished.connect(loop.quit)
    QTimer.singleShot(5000, loop.quit)
    loop.exec()
    assert dialog.exported and dialog.review_issues == issues
    with ZipFile(dialog.exported[0]) as stream:
        assert stream.testzip() is None
        pngs = [name for name in stream.namelist() if name.endswith('.png')]
        assert len(pngs) == 1 and stream.read(pngs[0]) == originals
    reopened = SetExportDialog(images[:1], review_issues=issues, membership=dialog.saved_membership)
    assert not reopened.ready_only.isChecked()
    assert not reopened.export_button.isEnabled()
    reopened.close()
    dialog.close()


def test_partial_export_does_not_override_ambiguous_or_invalid_png(images):
    from studio_alpha_qc import AlphaQcIssue, AlphaQcReport
    missing = {'kind': 'missing', 'object_id': 'missing', 'count': 0, 'paths': []}
    ambiguous = {'kind': 'ambiguous', 'object_id': 'two', 'count': 2, 'paths': [str(p) for p in images[:2]]}
    dialog = SetExportDialog(images, review_issues=[missing, ambiguous])
    dialog.ready_only.setChecked(True)
    assert not dialog.export_button.isEnabled()
    assert dialog._blocking_review_issues() == [ambiguous]
    dialog.close()
    report = AlphaQcReport(str(images[0].resolve()), 'block',
        (AlphaQcIssue('opaque', 'block', 'PNG непрозрачен.', 'Проверьте фон.'),), width=32, height=32)
    dialog = SetExportDialog(images[:1], review_issues=[missing], quality_reports=[report])
    dialog.ready_only.setChecked(True)
    assert not dialog.export_button.isEnabled()
    dialog._export()
    assert dialog.worker is None
    assert 'блокируют экспорт' in dialog.status.text()
    dialog.close()


def test_empty_export_table_and_column_selection_are_reachable(images):
    empty = SetExportDialog([])
    assert empty.table.rowCount() == 0
    assert empty.summary_counts.text() == '0 изображений · 0 наборов'
    assert not empty.export_button.isEnabled()
    empty.close()
    dialog = SetExportDialog(images, membership=_membership_for_sets(images, ['Mini', 'Custom']))
    assert not dialog.rename_set_button.isEnabled()
    dialog.table.horizontalHeader().sectionClicked.emit(2)
    assert dialog.rename_set_button.isEnabled()
    assert dialog._editing_set_id == dialog._set_columns[1][0]
    dialog.close()


def test_translation_choice_skips_latin_names_and_falls_back_without_key(images):
    dialog = SetExportDialog(images, project_name='Little Goose', name_translator=None)
    latin = [{'title': 'Characters', 'images': [images[0]]}]
    assert dialog._choose_translation(latin) is None
    cyrillic = [{'title': 'Персонажи', 'images': [images[0]]}]
    assert dialog._choose_translation(cyrillic) is None  # no key: transliteration, not blocked
    assert 'транслит' in dialog._translation_notice
    dialog.reject()


def test_translation_choice_asks_once_and_honours_buttons(images, monkeypatch):
    class Translator:
        label = 'KIE · Test'
        def __call__(self, names):
            return {}
    translator = Translator()
    dialog = SetExportDialog(images, project_name='Гуси', name_translator=translator)
    groups = [{'title': 'Персонажи', 'images': [images[0]]}]
    from PyQt6.QtWidgets import QMessageBox
    for button_text, expected in (('Перевести', translator), ('Без перевода (транслит)', None), ('Отмена', False)):
        def fake_exec(box, text=button_text):
            for button in box.buttons():
                if button.text() == text:
                    box._clicked = button
        monkeypatch.setattr(QMessageBox, 'exec', fake_exec)
        monkeypatch.setattr(QMessageBox, 'clickedButton', lambda box: getattr(box, '_clicked', None))
        assert dialog._choose_translation(groups) is expected
    dialog.reject()


def test_png_check_screen_filter_picture_and_single_export_button(images):
    from studio_alpha_qc import AlphaQcIssue, AlphaQcReport
    membership = _membership_for_sets(images[:2], ['Мини'])
    ok = AlphaQcReport(str(images[0].resolve()), 'ok', (), width=32, height=32)
    review = AlphaQcReport(
        str(images[1].resolve()), 'review',
        (AlphaQcIssue('touches_edge', 'review', 'Видимые пиксели доходят до края холста.', 'Проверьте края.'),),
        width=32, height=32,
    )
    dialog = SetExportDialog(images[:2], membership=membership, quality_reports=[ok, review])
    dialog._show_quality_review()
    # no filter buttons any more: every PNG is listed and problems are marked on the picture
    assert dialog.quality_filter_problems.isHidden() and dialog.quality_filter_all.isHidden()
    assert dialog.quality_list.count() == 2 and dialog.quality_list.currentRow() == 0
    assert not dialog.quality_picture._base.isNull()
    assert dialog.quality_fix_button.text() == 'Редактировать прозрачность'
    assert dialog.quality_fix_button.isEnabled()  # also for a file the automatic check found fine
    assert dialog.quality_export_button.isHidden()
    dialog.reject()


def test_png_check_screen_asks_before_exporting_when_not_all_images_are_checked(images, monkeypatch):
    from studio_alpha_qc import AlphaQcReport
    membership = _membership_for_sets(images, ['Мини'])
    reports = [AlphaQcReport(str(path.resolve()), 'ok', (), width=32, height=32) for path in images]
    dialog = SetExportDialog(images, membership=membership, quality_reports=reports)
    dialog.enable_marks({str(path.resolve()): 'unchecked' for path in images})
    dialog._show_quality_review()
    assert dialog._viewed_counts() == (0, 3)  # opening a picture is not checking it when «Ок» can be given
    dialog.quality_list.setCurrentRow(0)
    dialog.quality_mark_buttons['ok'].click()
    assert dialog._viewed_counts() == (1, 3)
    asked = []
    monkeypatch.setattr(dialog, '_confirm_unviewed', lambda viewed, total: asked.append((viewed, total)) or False)
    dialog._export()
    assert asked == [(1, 3)] and dialog.stack.currentWidget() is dialog.quality_page
    assert dialog.quality_list.currentRow() == 1  # sent to the first picture not checked yet
    assert dialog.worker is None
    dialog.reject()


def test_png_check_screen_without_marks_counts_opened_pictures_as_checked(images):
    from studio_alpha_qc import AlphaQcReport
    membership = _membership_for_sets(images, ['Мини'])
    reports = [AlphaQcReport(str(path.resolve()), 'ok', (), width=32, height=32) for path in images]
    dialog = SetExportDialog(images, membership=membership, quality_reports=reports)
    dialog._show_quality_review()
    assert dialog._viewed_counts() == (1, 3)
    dialog.quality_list.setCurrentRow(1)
    assert dialog._viewed_counts() == (2, 3)
    dialog.reject()


def test_png_check_screen_quick_marks_use_the_results_step_marks(images):
    from studio_alpha_qc import AlphaQcReport
    membership = _membership_for_sets(images, ['Мини'])
    reports = [AlphaQcReport(str(path.resolve()), 'ok', (), width=32, height=32) for path in images]
    dialog = SetExportDialog(images, membership=membership, quality_reports=reports)
    dialog.enable_marks({str(path.resolve()): 'ok' for path in images})
    dialog._show_quality_review()
    sent = []
    dialog.mark_requested.connect(lambda path, mark: sent.append((path, mark)))
    assert not dialog.quality_marks_row.isHidden()
    assert dialog.quality_mark_buttons['ok'].isChecked()
    dialog.quality_mark_buttons['bad_cutout'].click()
    assert sent == [(str(images[0].resolve()), 'bad_cutout')]
    assert dialog.quality_mark_buttons['bad_cutout'].isChecked() and not dialog.quality_mark_buttons['ok'].isChecked()
    assert 'Брак вырезания' in dialog.quality_list.item(0).toolTip()
    dialog.reject()


def test_png_check_screen_shows_the_new_mark_before_the_slow_save_runs(images):
    from studio_alpha_qc import AlphaQcReport
    membership = _membership_for_sets(images, ['Мини'])
    reports = [AlphaQcReport(str(path.resolve()), 'ok', (), width=32, height=32) for path in images]
    dialog = SetExportDialog(images, membership=membership, quality_reports=reports)
    dialog.enable_marks({str(path.resolve()): 'bad_cutout' for path in images})
    dialog._show_quality_review()
    lit_while_saving = []

    def slow_save(_path, _mark):  # the real handler writes the project here, taking seconds on a big run
        lit_while_saving.append([key for key, button in dialog.quality_mark_buttons.items() if button.isChecked()])

    dialog.mark_requested.connect(slow_save)
    dialog.quality_mark_buttons['ok'].click()
    assert lit_while_saving == [['ok']]
    dialog.reject()


def test_png_check_screen_hides_quick_marks_when_the_flow_has_none(images):
    from studio_alpha_qc import AlphaQcReport
    membership = _membership_for_sets(images[:1], ['Мини'])
    dialog = SetExportDialog(images[:1], membership=membership,
                             quality_reports=[AlphaQcReport(str(images[0].resolve()), 'ok', (), width=32, height=32)])
    dialog._show_quality_review()
    assert dialog.quality_marks_row.isHidden()
    dialog.reject()


def test_png_check_loads_one_by_one_off_ui_thread_and_gates_export(tmp_path):
    from PIL import Image
    from PyQt6.QtCore import QCoreApplication
    from studio_alpha_qc import inspect_alpha_png
    from studio_set_export_ui import SetExportDialog
    import threading
    import time

    app = QApplication.instance() or QApplication([])
    paths = []
    for index in range(3):
        path = tmp_path / f'item_{index}.png'
        image = Image.new('RGBA', (64, 64), (0, 0, 0, 0))
        image.paste((200, 50, 50, 255), (20, 20, 44, 44))
        image.save(path)
        paths.append(path)
    threads = []

    def loader(path):
        threads.append(threading.current_thread())
        return inspect_alpha_png(path)

    dialog = SetExportDialog(paths, embedded=True, quality_loader=loader)
    assert not dialog.export_button.isEnabled()  # verdicts unknown yet
    deadline = time.monotonic() + 15
    while dialog._qc_pending and time.monotonic() < deadline:
        QCoreApplication.processEvents()
        time.sleep(0.01)
    assert dialog._qc_pending == 0 and len(dialog.quality_reports) == 3
    assert all(thread is not threading.main_thread() for thread in threads)
    assert dialog.export_button.isEnabled()
    dialog.quality_background_buttons['#000000'].click()  # black
    assert dialog.quality_background_buttons['#000000'].isChecked()
    assert not dialog.quality_background_buttons['checkerboard'].isChecked()
    assert dialog._quality_background == '#000000'
    assert dialog.quality_picture._background == '#000000'
    dialog._stop_png_check()
    app.processEvents()


def test_png_check_picture_zooms_pans_and_fits(images):
    from PyQt6.QtCore import QPoint, QPointF, Qt
    from PyQt6.QtGui import QMouseEvent, QWheelEvent
    from studio_alpha_qc import AlphaQcReport
    membership = _membership_for_sets(images[:1], ['Мини'])
    dialog = SetExportDialog(images[:1], membership=membership,
                             quality_reports=[AlphaQcReport(str(images[0].resolve()), 'ok', (), width=32, height=32)])
    dialog.resize(1120, 700)
    dialog.show()
    dialog._show_quality_review()
    picture = dialog.quality_picture
    assert picture._zoom == 1.0

    def wheel(delta, modifiers):
        event = QWheelEvent(QPointF(picture.width() / 2, picture.height() / 2), QPointF(), QPoint(0, 0), QPoint(0, delta),
                            Qt.MouseButton.NoButton, modifiers, Qt.ScrollPhase.NoScrollPhase, False)
        picture.wheelEvent(event)

    wheel(120, Qt.KeyboardModifier.NoModifier)
    assert picture._zoom == 1.0  # a bare wheel does not zoom
    wheel(120, Qt.KeyboardModifier.ControlModifier)
    assert picture._zoom > 1.0
    zoomed = picture._zoom
    start = QPointF(picture._offset)
    press = QMouseEvent(QMouseEvent.Type.MouseButtonPress, QPointF(50, 50), Qt.MouseButton.MiddleButton,
                        Qt.MouseButton.MiddleButton, Qt.KeyboardModifier.NoModifier)
    move = QMouseEvent(QMouseEvent.Type.MouseMove, QPointF(80, 70), Qt.MouseButton.NoButton,
                       Qt.MouseButton.MiddleButton, Qt.KeyboardModifier.NoModifier)
    release = QMouseEvent(QMouseEvent.Type.MouseButtonRelease, QPointF(80, 70), Qt.MouseButton.MiddleButton,
                          Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier)
    picture.mousePressEvent(press)
    picture.mouseMoveEvent(move)
    picture.mouseReleaseEvent(release)
    assert picture._offset != start and picture._zoom == zoomed
    picture.mouseDoubleClickEvent(QMouseEvent(QMouseEvent.Type.MouseButtonDblClick, QPointF(50, 50),
                                              Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton,
                                              Qt.KeyboardModifier.NoModifier))
    assert picture._zoom == 1.0 and picture._offset == QPointF(0.0, 0.0)
    dialog.reject()


def test_png_check_marks_a_flagged_picture_until_the_owner_says_ok(images):
    from studio_alpha_qc import AlphaQcIssue, AlphaQcReport
    membership = _membership_for_sets(images[:2], ['Мини'])
    flagged = AlphaQcReport(str(images[0].resolve()), 'review',
                            (AlphaQcIssue('touches_edge', 'review', 'Доходит до края.', 'Проверьте.'),), width=32, height=32)
    fine = AlphaQcReport(str(images[1].resolve()), 'ok', (), width=32, height=32)
    dialog = SetExportDialog(images[:2], membership=membership, quality_reports=[flagged, fine])
    dialog.enable_marks({str(images[0].resolve()): 'unchecked', str(images[1].resolve()): 'unchecked'})
    dialog._show_quality_review()
    key = str(images[0].resolve())
    assert dialog._needs_attention(key) and not dialog._needs_attention(str(images[1].resolve()))
    dialog.quality_list.setCurrentRow(0)
    dialog.quality_mark_buttons['ok'].click()
    assert not dialog._needs_attention(key)  # «Ок» removes the «!»
    assert dialog._viewed_counts() == (1, 2)  # the other picture has not been checked yet
    dialog.reject()


def test_png_check_screen_marks_are_mutually_exclusive_for_every_pair(images):
    from studio_alpha_qc import AlphaQcReport
    membership = _membership_for_sets(images, ['Мини'])
    reports = [AlphaQcReport(str(path.resolve()), 'ok', (), width=32, height=32) for path in images]
    dialog = SetExportDialog(images, membership=membership, quality_reports=reports)
    dialog.enable_marks({str(path.resolve()): 'ok' for path in images})
    dialog._show_quality_review()
    buttons = dialog.quality_mark_buttons
    for first in buttons:
        for second in buttons:
            buttons[first].click()
            buttons[second].click()
            assert [key for key, button in buttons.items() if button.isChecked()] == [second]
    dialog.reject()


def test_png_check_screen_follows_marks_set_elsewhere(images):
    from studio_alpha_qc import AlphaQcReport
    membership = _membership_for_sets(images, ['Мини'])
    reports = [AlphaQcReport(str(path.resolve()), 'ok', (), width=32, height=32) for path in images]
    dialog = SetExportDialog(images, membership=membership, quality_reports=reports)
    dialog.enable_marks({str(path.resolve()): 'ok' for path in images})
    dialog._show_quality_review()
    dialog.enable_marks({str(path.resolve()): 'bad_cutout' for path in images})  # set in the editor meanwhile
    assert dialog.quality_mark_buttons['bad_cutout'].isChecked() and not dialog.quality_mark_buttons['ok'].isChecked()
    assert 'Брак вырезания' in dialog.quality_list.item(0).toolTip()
    dialog.reject()


def test_thumbnail_cache_on_disk_serves_second_read_and_ignores_a_changed_file(images, tmp_path):
    import os
    from studio_set_export_ui import read_thumbnail, thumb_cache_dir
    cache = thumb_cache_dir(tmp_path)
    assert cache == tmp_path / '.thumb-cache' and thumb_cache_dir(None) is None
    first = read_thumbnail(images[0], 120, cache)
    assert not first.isNull() and len(list(cache.glob('*.png'))) == 1
    cached_file = next(cache.glob('*.png'))
    stamp_before = cached_file.stat().st_mtime
    again = read_thumbnail(images[0], 120, cache)
    assert again.size() == first.size() and len(list(cache.glob('*.png'))) == 1  # served from disk, no second entry
    assert cached_file.stat().st_mtime >= stamp_before
    # the picture is regenerated or edited: another size/time, so a new entry and never the stale thumbnail
    Image.new('RGBA', (64, 48), (200, 20, 20, 255)).save(images[0])
    changed = read_thumbnail(images[0], 120, cache)
    assert len(list(cache.glob('*.png'))) == 2 and changed.size() != first.size()
    assert not list(cache.glob('*.tmp.png'))


def test_thumbnail_cache_is_pruned_least_recently_used_first(tmp_path):
    import os
    from studio_set_export_ui import prune_thumb_cache
    cache = tmp_path / '.thumb-cache'
    cache.mkdir()
    for n in range(6):
        file = cache / f'{n}.png'
        file.write_bytes(b'x' * 10)
        os.utime(file, (1000 + n, 1000 + n))
    (cache / 'keep.txt').write_text('not a thumbnail')
    prune_thumb_cache(cache, max_files=3, max_bytes=10_000)
    assert sorted(file.name for file in cache.glob('*.png')) == ['3.png', '4.png', '5.png']
    assert (cache / 'keep.txt').exists()
    prune_thumb_cache(cache, max_files=100, max_bytes=20)
    assert sorted(file.name for file in cache.glob('*.png')) == ['4.png', '5.png']


def test_png_check_lists_every_picture_at_once_while_the_check_runs(images):
    from studio_alpha_qc import AlphaQcReport
    membership = _membership_for_sets(images, ['Мини'])
    dialog = SetExportDialog(images, membership=membership, quality_reports=[],
                             quality_loader=lambda path: None)
    dialog._stop_png_check()
    dialog._qc_pending = len(images)  # the check has not delivered anything yet
    dialog._show_quality_review()
    assert dialog.quality_list.count() == len(images)
    assert [dialog.quality_list.item(row).text() for row in range(len(images))] == [path.name for path in images]
    assert all(not (dialog.quality_list.item(row).flags() & Qt.ItemFlag.ItemIsSelectable) for row in range(len(images)))
    assert dialog._current_quality_key() == ''
    dialog.quality_reports[str(images[1].resolve())] = AlphaQcReport(str(images[1].resolve()), 'ok', (), width=32, height=32)
    dialog._refresh_quality_page()
    assert dialog.quality_list.count() == len(images)
    assert dialog._current_quality_key() == str(images[1].resolve())  # the first real picture gets the selection
    dialog._qc_pending = 0
    dialog._refresh_quality_page()
    assert dialog.quality_list.count() == 1  # unchecked pictures are not listed once the check is over
    dialog.reject()


def test_png_check_buttons_fit_a_1120_px_window_in_two_rows(images):
    from studio_alpha_qc import AlphaQcReport
    membership = _membership_for_sets(images, ['Мини'])
    reports = [AlphaQcReport(str(path.resolve()), 'ok', (), width=32, height=32) for path in images]
    dialog = SetExportDialog(images, membership=membership, quality_reports=reports)
    dialog.enable_marks({str(path.resolve()): 'bad_generation' for path in images})
    dialog._show_quality_review()
    dialog.resize(1120, 780)
    dialog.show()
    QApplication.processEvents()
    assert dialog.minimumSizeHint().width() <= 1120
    # marks and «Исключить» above, the actions on this picture below
    assert dialog.quality_exclude_button.y() < dialog.quality_prompt_button.y()
    assert dialog.quality_prompt_button.y() == dialog.quality_regenerate_button.y() == dialog.quality_fix_button.y()
    for button in dialog.quality_mark_buttons.values():
        assert button.width() >= button.fontMetrics().horizontalAdvance(button.text())
    dialog.reject()
