import numpy as np
import pytest
from unittest.mock import patch
from PIL import Image

from studio_contour import BezierNode, BezierPath
from studio_contour_session import ContourEditSession


def square(x0, y0, x1, y1, shape):
    return BezierPath(tuple(BezierNode(point) for point in ((x0, y0), (x1, y0), (x1, y1), (x0, y1))), 255, shape)


def rgba_fixture():
    rgba = np.zeros((30, 30, 4), np.uint8)
    rgba[..., 0] = 13
    rgba[..., 1] = 101
    rgba[..., 2] = 209
    rgba[5:15, 5:15, 3] = 255
    return rgba


def test_session_preserves_original_rgb_and_roi_outside_after_edit():
    rgba = rgba_fixture()
    session = ContourEditSession(rgba)
    old = square(5, 5, 14, 14, rgba.shape[:2])
    index = next(i for i, path in enumerate(session.document.paths) if path.fill_value == 255)
    before = session.document.alpha.copy()
    session.document.apply_path(index, square(8, 5, 17, 14, rgba.shape[:2]), (3, 3, 20, 18))
    current = session.current_rgba()
    outside = np.ones(before.shape, bool)
    outside[3:18, 3:20] = False
    assert np.array_equal(session.document.alpha[outside], before[outside])
    assert np.array_equal(current[..., :3], rgba[..., :3])
    assert np.array_equal(session.original_rgba, rgba)
    assert old.source_shape == rgba.shape[:2]  # fixture geometry uses final pixels


def test_checkpoint_undo_redo_and_reset_are_bounded():
    rgba = rgba_fixture()
    session = ContourEditSession(rgba, history_limit=2, history_bytes=rgba.shape[0] * rgba.shape[1] * 2)
    original = session.document.alpha.copy()
    index = next(i for i, path in enumerate(session.document.paths) if path.fill_value == 255)
    session.document.apply_path(index, square(7, 5, 16, 14, rgba.shape[:2]), (2, 2, 20, 18))
    changed = session.document.alpha.copy()
    assert session.checkpoint()
    assert session.can_undo
    assert session.undo()
    assert np.array_equal(session.document.alpha, original)
    assert session.redo()
    assert np.array_equal(session.document.alpha, changed)
    assert session.reset()
    assert np.array_equal(session.document.alpha, original)
    assert not session.can_redo
    assert session.undo()  # Reset is a normal undoable action.
    assert np.array_equal(session.document.alpha, changed)
    assert session.history_bytes <= rgba.shape[0] * rgba.shape[1] * 2


def test_save_copy_writes_new_png_and_refuses_existing_or_bad_destination(tmp_path):
    rgba = rgba_fixture()
    source = rgba.copy()
    session = ContourEditSession(rgba)
    output = tmp_path / "edited.png"
    assert session.save_copy(output) == output
    saved = np.asarray(Image.open(output).convert("RGBA"))
    assert np.array_equal(saved[..., :3], source[..., :3])
    assert np.array_equal(saved[..., 3], session.document.alpha)
    assert np.array_equal(source, rgba)
    saved_bytes = output.read_bytes()
    with pytest.raises(FileExistsError):
        session.save_copy(output)
    assert output.read_bytes() == saved_bytes
    with pytest.raises(FileNotFoundError):
        session.save_copy(tmp_path / "missing" / "edited.png")
    assert np.array_equal(source, rgba)


def test_history_limit_one_retains_latest_checkpoint_and_invalidates_stale_redo():
    rgba = rgba_fixture()
    session = ContourEditSession(rgba, history_limit=1, history_bytes=rgba.shape[0] * rgba.shape[1] * 2)
    index = next(i for i, path in enumerate(session.document.paths) if path.fill_value == 255)
    session.document.apply_path(index, square(7, 5, 16, 14, rgba.shape[:2]), (2, 2, 20, 18))
    first = session.document.alpha.copy()
    assert session.checkpoint()
    index = next(i for i, path in enumerate(session.document.paths) if path.fill_value == 255)
    session.document.apply_path(index, square(9, 5, 18, 14, rgba.shape[:2]), (2, 2, 22, 18))
    latest = session.document.alpha.copy()
    assert session.checkpoint()
    assert not session.checkpoint()
    assert np.array_equal(session.document.alpha, latest)
    assert session.undo()
    assert np.array_equal(session.document.alpha, first)
    assert not session.can_undo
    assert session.redo()
    assert np.array_equal(session.document.alpha, latest)
    assert session.undo()
    # A direct edit after Undo must discard the old redo future.
    index = next(i for i, path in enumerate(session.document.paths) if path.fill_value == 255)
    session.document.apply_path(index, square(6, 5, 15, 14, rgba.shape[:2]), (2, 2, 20, 18))
    assert not session.redo()
    assert not session.can_redo


def test_atomic_save_failure_leaves_no_destination_or_partial_file(tmp_path, monkeypatch):
    rgba = rgba_fixture()
    source = rgba.copy()
    session = ContourEditSession(rgba)
    output = tmp_path / "failed.png"

    def fail_save(*args, **kwargs):
        raise OSError("simulated PNG failure")

    monkeypatch.setattr(Image.Image, "save", fail_save)
    with pytest.raises(OSError, match="simulated"):
        session.save_copy(output)
    assert not output.exists()
    assert list(tmp_path.iterdir()) == []
    assert np.array_equal(session.original_rgba, source)


@pytest.mark.parametrize('byte_cap', [2, 10])
def test_evicted_history_never_jumps_over_an_edit(byte_cap):
    rgba = rgba_fixture()
    session = ContourEditSession(rgba, history_limit=2, history_bytes=900 * byte_cap)
    states = [session.document.alpha.copy()]
    for x in (6, 7, 8):
        session.document.alpha[8, x] = 0
        session.checkpoint()
        states.append(session.document.alpha.copy())
    index = 3
    while session.can_undo:
        assert session.undo()
        index -= 1
        assert np.array_equal(session.document.alpha, states[index])
        assert session.history_bytes <= 900 * byte_cap
    assert index >= 1
    while session.can_redo:
        assert session.redo()
        index += 1
        assert np.array_equal(session.document.alpha, states[index])
    assert index == 3
    assert session.reset()
    assert np.array_equal(session.document.alpha, states[0])


def test_rejects_invalid_rgba_and_history_limits():
    with pytest.raises(TypeError):
        ContourEditSession(np.zeros((3, 3, 3), np.uint8))
    with pytest.raises(ValueError):
        ContourEditSession(np.zeros((3, 3, 4), np.uint8), history_limit=0)
    with pytest.raises(ValueError):
        ContourEditSession(np.zeros((3, 3, 4), np.uint8), history_bytes=8)


def test_history_pressure_keeps_current_checkpoint_instead_of_stale_redo():
    rgba = rgba_fixture()
    session = ContourEditSession(rgba, history_bytes=rgba.shape[0] * rgba.shape[1])
    session.document.alpha[8, 8] = 0
    session.checkpoint()
    checkpoint = session.document.alpha.copy()
    session.document.alpha[9, 9] = 0
    assert session.undo()
    assert np.array_equal(session.document.alpha, checkpoint)
    assert not session.can_redo  # Evicted to retain the current one-snapshot baseline.
    assert not session.checkpoint()  # The baseline was not accidentally evicted.
    assert session.history_bytes <= rgba.shape[0] * rgba.shape[1]


def test_lazy_session_does_not_extract_on_open_brush_or_history():
    with patch("studio_contour.extract_contours", side_effect=AssertionError("unexpected extraction")):
        session = ContourEditSession(rgba_fixture(), extract_paths=False)
        session.document.alpha[8, 8] = 0
        session.checkpoint()
        assert session.undo()
        assert session.redo()
        assert session.reset()
        assert session.document.paths == []
