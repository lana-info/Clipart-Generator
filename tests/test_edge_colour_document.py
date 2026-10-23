"""RGB retouching must share alpha history without changing its geometry."""
from unittest.mock import patch

import numpy as np
from PIL import Image
import pytest

from v3_transparency_preview import MaskEditDocument


@pytest.fixture
def document():
    rgba = np.full((32, 40, 4), (70, 130, 200, 255), dtype=np.uint8)
    rgba[:4, :, 3] = 0
    rgba[4:12, :, 3] = 96
    return MaskEditDocument(Image.fromarray(rgba))


def proposal():
    return Image.new('RGB', (8, 10), (220, 180, 90)), (8, 8, 16, 18)


def test_rgb_apply_undo_redo_is_one_step_and_alpha_and_source_stay_exact(document):
    before = document.corrected_image().tobytes()
    source = document.image.tobytes()
    alpha = document.mask.tobytes()
    rgb, bounds = proposal()
    document.apply_rgb_proposal(rgb, bounds)
    after = document.corrected_image().tobytes()
    assert after != before and document.is_dirty and document.is_rgb_dirty
    assert document.mask.tobytes() == alpha
    assert document._original_image.tobytes() == source
    assert len(document._undo) == 1 and document.history_bytes == 8 * 10 * 6
    document.undo()
    assert document.corrected_image().tobytes() == before
    assert not document.is_dirty
    document.redo()
    assert document.corrected_image().tobytes() == after
    assert document.mask.tobytes() == alpha
    assert document.image.getchannel('A').tobytes() == document._original_mask.tobytes()


def test_rgb_and_brush_share_ordered_history(document):
    rgb, bounds = proposal()
    document.apply_rgb_proposal(rgb, bounds)
    coloured = document.corrected_image().tobytes()
    document.begin_stroke()
    document.extend_stroke([(28, 20)], radius=3, action='remove', hardness=100)
    document.end_stroke()
    painted = document.corrected_image().tobytes()
    document.undo()
    assert document.corrected_image().tobytes() == coloured
    document.undo()
    assert not document.is_dirty
    document.redo()
    document.redo()
    assert document.corrected_image().tobytes() == painted


def test_rgb_reset_restores_source_as_one_undo_step(document):
    original = document.corrected_image().tobytes()
    rgb, bounds = proposal()
    document.apply_rgb_proposal(rgb, bounds)
    document.begin_stroke()
    document.extend_stroke([(26, 22)], radius=2, action='remove', hardness=100)
    document.end_stroke()
    before_reset = document.corrected_image().tobytes()
    history = len(document._undo)
    document.reset()
    assert document.corrected_image().tobytes() == original
    assert len(document._undo) == history + 1
    document.undo()
    assert document.corrected_image().tobytes() == before_reset
    document.redo()
    assert document.corrected_image().tobytes() == original


def test_save_copy_rebinds_rgb_and_alpha_and_keeps_saved_baseline(document, tmp_path):
    document._save_info['dpi'] = (300, 300)
    rgb, bounds = proposal()
    document.apply_rgb_proposal(rgb, bounds)
    png, mask = tmp_path / 'edited.png', tmp_path / 'edited.mask.png'
    expected = document.corrected_image().tobytes()
    document.save(png, mask)
    with Image.open(png) as saved:
        assert saved.convert('RGBA').tobytes() == expected
        assert abs(saved.info['dpi'][0] - 300) < .01
    assert not document.is_dirty
    document.undo()
    assert document.is_dirty
    document.redo()
    assert not document.is_dirty
    document.apply_rgb_proposal(Image.new('RGB', rgb.size, (10, 30, 60)), bounds)
    assert document.is_rgb_dirty
    with Image.open(png) as saved:
        assert saved.convert('RGBA').tobytes() == expected


def test_failed_save_preserves_rgb_dirty_history_and_existing_files(document, tmp_path):
    png, mask = tmp_path / 'edited.png', tmp_path / 'edited.mask.png'
    document.save(png, mask)
    old = png.read_bytes(), mask.read_bytes()
    document.apply_rgb_proposal(*proposal())
    before = document.corrected_image().tobytes()
    with patch.object(document, '_replace_pair', side_effect=OSError('write failed')):
        with pytest.raises(OSError):
            document.save(png, mask)
    assert document.is_rgb_dirty and document.can_undo
    assert document.corrected_image().tobytes() == before
    assert (png.read_bytes(), mask.read_bytes()) == old


def test_rgb_budget_refusal_is_atomic(document):
    document.HISTORY_MEMORY_LIMIT = 100
    before = document.corrected_image().tobytes()
    with pytest.raises(ValueError, match='памяти'):
        document.apply_rgb_proposal(*proposal())
    assert document.corrected_image().tobytes() == before
    assert not document.can_undo and not document.is_dirty


@pytest.mark.parametrize('bounds', [(-1, 8, 7, 18), (8, 8, 41, 18), (8, 8, 8, 18), (8., 8, 16, 18)])
def test_invalid_rgb_bounds_do_not_mutate(document, bounds):
    before = document.corrected_image().tobytes()
    with pytest.raises(ValueError):
        document.apply_rgb_proposal(Image.new('RGB', (8, 10)), bounds)
    assert document.corrected_image().tobytes() == before and not document.can_undo


def test_rgb_noop_and_invisible_edit_do_not_create_history(document):
    bounds = (8, 8, 16, 18)
    document.apply_rgb_proposal(document.image.crop(bounds).convert('RGB'), bounds)
    assert not document.can_undo
    with pytest.raises(ValueError, match='прозрач'):
        document.apply_rgb_proposal(Image.new('RGB', (8, 2)), (8, 0, 16, 2))
    assert not document.can_undo and not document.is_dirty


def test_rgb_draft_roundtrip_preserves_original_and_dirty_baselines(document):
    original = document.corrected_image().tobytes()
    document.apply_rgb_proposal(*proposal())
    document.begin_stroke()
    document.extend_stroke([(12, 12)], radius=3, action='remove', hardness=100)
    document.end_stroke()
    expected = document.corrected_image().tobytes()
    draft = document.export_rgb_draft()
    restored = MaskEditDocument(document._original_image)
    restored.mask = document.mask.copy()
    restored.restore_rgb_draft(draft)
    assert restored.corrected_image().tobytes() == expected
    assert restored.is_rgb_dirty and restored.is_dirty
    assert not restored.can_undo  # File switching retains existing history policy.
    restored.reset()
    assert restored.corrected_image().tobytes() == original
    restored.undo()
    assert restored.corrected_image().tobytes() == expected


def test_clean_or_saved_rgb_has_no_draft(document, tmp_path):
    assert document.export_rgb_draft() is None
    document.apply_rgb_proposal(*proposal())
    document.save(tmp_path / 'edited.png', tmp_path / 'edited.mask.png')
    assert document.export_rgb_draft() is None


def test_mismatched_rgb_draft_is_rejected_before_pixels_change(document):
    from io import BytesIO
    encoded = BytesIO()
    Image.new('RGB', (20, 20)).save(encoded, format='PNG')
    original = document.corrected_image().tobytes()
    with pytest.raises(ValueError):
        document.restore_rgb_draft(((8, 8, 16, 18), encoded.getvalue()))
    assert document.corrected_image().tobytes() == original
    assert not document.is_dirty and not document.can_undo


def test_rgb_copy_rebinds_generation_record_without_touching_source(document, tmp_path):
    from chroma_generation_record import (
        bind_generation_record, capture_generation_record, load_generation_color,
        load_generation_result_kind, record_path, write_generation_intent,
    )
    source = tmp_path / 'source.png'
    intent = write_generation_intent(source, color='blue', prompt='safe test', result_kind='clipart')
    document.corrected_image().save(source)
    bind_generation_record(source, intent, stage='final')
    before = source.read_bytes(), record_path(source).read_bytes()
    document.apply_rgb_proposal(*proposal())
    output = tmp_path / 'source_edited.png'
    document.save(output, tmp_path / 'source_edited.mask.png', copy_source=source)
    rebound = capture_generation_record(output)
    assert rebound['source_sha256'] != capture_generation_record(source)['source_sha256']
    assert rebound['prompt_sha256'] == intent['prompt_sha256']
    assert load_generation_result_kind(output) == 'clipart'
    assert load_generation_color(output) is None
    assert (source.read_bytes(), record_path(source).read_bytes()) == before
