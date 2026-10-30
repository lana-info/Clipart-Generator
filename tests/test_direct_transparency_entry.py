import hashlib
import pytest
from PIL import Image
from PyQt6.QtWidgets import QApplication
from studio_workflow_host import WorkflowHost
from v3_processing_flow import install_processing_flow
from v3_project_state import ProjectState, ProjectMode, StepId
from v3_wizard import AppShell


@pytest.fixture(scope='module')
def app():
    return QApplication.instance() or QApplication([])


def setup_editor(tmp_path, app, sources=None, state=None):
    state = state or ProjectState(mode=ProjectMode.PROCESSING)
    state.common.work_dir = str(tmp_path)
    shell = AppShell(state)
    controller = install_processing_flow(WorkflowHost(shell,'processing'))
    if sources is not None:
        controller.files_page.add_files([str(p) for p in sources])
    app.processEvents()
    return shell,controller


def png(path, colour=(220,180,90,255)):
    path.parent.mkdir(parents=True,exist_ok=True)
    Image.new('RGBA',(24,24),colour).save(path)
    return path


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def entry(shell):
    # The live stepper control only: a whole-tree findChild can match stale
    # buttons from previous refreshes (they stay parented until a running event
    # loop processes the deferred deletion), and PyQt6 >= 6.10 returns the
    # oldest match, which disabled all entry assertions on developer machines.
    from v3_components import V3Button
    matches = [label for label in shell.step_labels
               if isinstance(label, V3Button) and label.objectName() == 'directTransparencyButton']
    assert len(matches) == 1, 'the stepper must show exactly one live transparency control'
    return matches[0]


def test_left_entry_only_enables_for_available_png_and_never_runs_worker(tmp_path,app):
    source=png(tmp_path/'inputs'/'sample.png')
    shell,c=setup_editor(tmp_path,app)
    assert entry(shell) is not None
    assert not entry(shell).isEnabled()
    c.files_page.add_files([str(source)])
    assert entry(shell).isEnabled()
    entry(shell).click()
    assert shell.state.current_step is StepId.TRANSPARENCY
    assert c.worker is None and c.run_queue.session is None
    assert c.pages[StepId.TRANSPARENCY].current_path == source
    c._close_transparency_editor()
    assert shell.state.current_step is StepId.FILES
    assert shell.state.processing.selected_files == [str(source)]
    shell.close()


def test_save_copy_preserves_source_and_existing_files_and_restores_editor(tmp_path,app):
    source=png(tmp_path/'inputs'/'sample.png');before=digest(source)
    shell,c=setup_editor(tmp_path,app,[source]);entry(shell).click()
    page=c.pages[StepId.TRANSPARENCY]
    doc=page.document;doc.begin_stroke();doc.extend_stroke(((10,10),),radius=3,action='remove',hardness=100);doc.end_stroke()
    first,mask=page.save_current()
    assert first != source and mask.is_file()
    assert digest(source) == before
    with Image.open(first) as saved:assert saved.getpixel((10,10))[3] == 0
    copy_hash=digest(first)
    second,_=page.save_current()
    assert second != first and digest(first)==copy_hash
    data=shell.state.to_dict()
    restored=ProjectState.from_dict(data)
    assert restored.processing.transparency_edits[str(source)] == str(second)
    new_shell,new_c=setup_editor(tmp_path,app,state=restored)
    new_page=new_c.pages[StepId.TRANSPARENCY]
    assert new_page.current_path == source
    assert new_page.document.mask.getpixel((10,10)) == 0
    new_c._close_transparency_editor()
    assert restored.current_step is StepId.FILES
    new_shell.close();shell.close()


def test_input_selection_does_not_recover_or_write_original_pairs(tmp_path,app,monkeypatch):
    from v3_transparency_preview import MaskEditDocument
    source=png(tmp_path/'inputs'/'sample.png')
    calls=[]
    monkeypatch.setattr(MaskEditDocument,'recover_pair',lambda *a,**k:calls.append(a))
    shell,c=setup_editor(tmp_path,app,[source]);entry(shell).click()
    assert calls == []
    assert list(source.parent.iterdir()) == [source]
    shell.close()


def test_deleted_input_and_other_formats_do_not_open_empty_editor(tmp_path,app):
    source=png(tmp_path/'sample.png')
    shell,c=setup_editor(tmp_path,app,[source]);source.unlink()
    entry(shell).click()
    assert shell.state.current_step is StepId.FILES
    c.files_page.clear_files()
    jpg=tmp_path/'sample.jpg';Image.new('RGB',(12,12)).save(jpg)
    c.files_page.add_files([str(jpg)])
    assert not entry(shell).isEnabled()
    shell.close()


def test_busy_queue_blocks_direct_navigation(tmp_path,app):
    from types import SimpleNamespace
    source=png(tmp_path/'sample.png');shell,c=setup_editor(tmp_path,app,[source])
    c.run_queue.session=SimpleNamespace(running=True)
    shell.refresh()
    assert not entry(shell).isEnabled()
    c.open_transparency_entry()
    assert shell.state.current_step is StepId.FILES
    c.run_queue.session=None;shell.close()


def test_direct_editor_does_not_mark_skipped_processing_steps_completed(tmp_path,app):
    source=png(tmp_path/'sample.png');shell,c=setup_editor(tmp_path,app,[source]);entry(shell).click()
    assert all('Пройден' not in label.accessibleName() for label in shell.step_labels[1:5])
    shell.close()


@pytest.mark.parametrize('stem',['a'*230,'я'*110])
def test_long_input_name_can_save_transactional_copy(tmp_path,app,stem):
    source=png(tmp_path/'inputs'/f'{stem}.png');before=digest(source)
    shell,c=setup_editor(tmp_path,app,[source]);entry(shell).click()
    output,mask=c.pages[StepId.TRANSPARENCY].save_current()
    assert output.is_file() and mask.is_file() and digest(source)==before
    shell.close()


def test_copy_failure_preserves_source_and_does_not_leave_empty_files(tmp_path,app,monkeypatch):
    source=png(tmp_path/'inputs'/'sample.png');before=digest(source)
    shell,c=setup_editor(tmp_path,app,[source]);entry(shell).click()
    page=c.pages[StepId.TRANSPARENCY]
    def fail(*args,**kwargs):raise OSError('simulated disk failure')
    monkeypatch.setattr(page.document,'save',fail)
    with pytest.raises(OSError):page.save_current()
    assert digest(source)==before and not list(page._save_dir.glob('*edited*.png'))
    assert not list(page._rough_dir.glob('*alpha-mask.png'))
    assert not shell.state.processing.transparency_edits
    shell.close()


def test_same_named_sources_save_distinct_copies_and_reject_outside_mapping(tmp_path,app):
    one=png(tmp_path/'one'/'sample.png');two=png(tmp_path/'two'/'sample.png',(1,2,3,255))
    shell,c=setup_editor(tmp_path,app,[one,two]);entry(shell).click()
    page=c.pages[StepId.TRANSPARENCY];first,_=page.save_current();page.file_list.setCurrentRow(1)
    second,_=page.save_current()
    assert first!=second
    assert set(shell.state.processing.transparency_edits)=={str(one),str(two)}
    page.set_files([one],save_dir=page._save_dir,rough_dir=page._rough_dir,saved_copies={str(one):str(two)})
    assert page.document.image.getpixel((0,0))==(220,180,90,255)
    shell.close()


def test_old_queue_editor_still_restores_to_results():
    state=ProjectState(mode=ProjectMode.PROCESSING);state.set_step(StepId.TRANSPARENCY)
    assert ProjectState.from_dict(state.to_dict()).current_step is StepId.RESULTS


@pytest.mark.parametrize('remove',['clear','remove','restart'])
def test_explicit_reimport_does_not_reopen_old_edited_copy(tmp_path,app,remove):
    source=png(tmp_path/'inputs'/'sample.png')
    shell,c=setup_editor(tmp_path,app,[source]);entry(shell).click()
    c.pages[StepId.TRANSPARENCY].save_current();c._close_transparency_editor()
    if remove=='clear':c.files_page.clear_files()
    elif remove=='remove':c.files_page.remove_file(str(source))
    else:c.start_processing_again()
    png(source,(0,0,255,255));c.files_page.add_files([str(source)]);entry(shell).click()
    assert c.pages[StepId.TRANSPARENCY].document.image.getpixel((0,0))==(0,0,255,255)
    shell.close()


def test_corrupt_saved_copy_does_not_block_original(tmp_path,app):
    source=png(tmp_path/'inputs'/'sample.png')
    shell,c=setup_editor(tmp_path,app,[source]);entry(shell).click()
    output,_=c.pages[StepId.TRANSPARENCY].save_current();output.write_bytes(b'not PNG')
    restored=ProjectState.from_dict(shell.state.to_dict())
    new_shell,new_c=setup_editor(tmp_path,app,state=restored)
    page=new_c.pages[StepId.TRANSPARENCY]
    assert page.document.image.getpixel((0,0))==(220,180,90,255)
    assert output.read_bytes()==b'not PNG'
    new_shell.close();shell.close()


@pytest.mark.parametrize('corruption',['huge-header','invalid-deflate'])
def test_crc_valid_corrupt_copy_falls_back_without_deleting(tmp_path,app,corruption):
    import struct,zlib
    source=png(tmp_path/'inputs'/'sample.png')
    shell,c=setup_editor(tmp_path,app,[source]);entry(shell).click()
    output,_=c.pages[StepId.TRANSPARENCY].save_current()
    data=output.read_bytes();result=data[:8];position=8
    while position<len(data):
        length=struct.unpack('>I',data[position:position+4])[0]
        kind=data[position+4:position+8];payload=data[position+8:position+8+length]
        if kind==b'IHDR' and corruption=='huge-header':payload=struct.pack('>II',20000,20000)+payload[8:]
        if kind==b'IDAT' and corruption=='invalid-deflate':payload=b'not-zlib'
        result+=struct.pack('>I',len(payload))+kind+payload+struct.pack('>I',zlib.crc32(kind+payload))
        position+=length+12
    output.write_bytes(result)
    restored=ProjectState.from_dict(shell.state.to_dict());new_shell,new_c=setup_editor(tmp_path,app,state=restored)
    page=new_c.pages[StepId.TRANSPARENCY]
    assert page.document.image.getpixel((0,0))==(220,180,90,255)
    assert output.read_bytes()==result
    assert 'Открыт исходный PNG' in page.contour_status.text()
    assert not page.contour_status.isHidden()
    new_shell.close();shell.close()


def test_direct_copy_keeps_metadata_and_hash_bound_generation_intent(tmp_path,app):
    from chroma_generation_record import write_generation_intent,bind_generation_record,capture_generation_record,record_path
    source=tmp_path/'inputs'/'sample.png';source.parent.mkdir()
    intent=write_generation_intent(source,color='blue',prompt='safe synthetic test')
    Image.new('RGBA',(24,24),(220,180,90,255)).save(source,dpi=(300,300),icc_profile=b'test-profile')
    bind_generation_record(source,intent)
    before=digest(source);sidecar_before=record_path(source).read_bytes()
    shell,c=setup_editor(tmp_path,app,[source]);entry(shell).click()
    output,_=c.pages[StepId.TRANSPARENCY].save_current()
    with Image.open(output) as image:
        assert abs(image.info['dpi'][0]-300)<0.1
        assert image.info['icc_profile']==b'test-profile'
    record=capture_generation_record(output)
    assert record['requested_color']=='blue' and record['source_sha256']==digest(output)
    assert digest(source)==before and record_path(source).read_bytes()==sidecar_before
    shell.close()


def test_save_copy_still_works_when_the_source_generation_record_no_longer_matches(tmp_path,app):
    """Owner 2026-10-27: «Не удалось сохранить PNG — Сведения генерации повреждены или относятся к другому файлу»."""
    from chroma_generation_record import write_generation_intent,bind_generation_record,capture_generation_record,record_path
    source=tmp_path/'inputs'/'sample.png';source.parent.mkdir()
    intent=write_generation_intent(source,color='blue',prompt='safe synthetic test')
    Image.new('RGBA',(24,24),(220,180,90,255)).save(source)
    bind_generation_record(source,intent)
    Image.new('RGBA',(24,24),(10,20,30,255)).save(source)  # the picture changed after the record was bound
    before=digest(source)
    with pytest.raises(ValueError):
        capture_generation_record(source)
    shell,c=setup_editor(tmp_path,app,[source]);entry(shell).click()
    output,_=c.pages[StepId.TRANSPARENCY].save_current()
    assert output.is_file() and digest(source)==before
    assert capture_generation_record(output) is None  # the stale record is not carried over to the copy
    assert record_path(source).is_file()
    shell.close()
