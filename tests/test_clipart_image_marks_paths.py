from pathlib import Path
from types import SimpleNamespace

from studio_clipart_review_ui import ImageReview


def _review(tmp_path):
    first, second = tmp_path / "a.png", tmp_path / "b.png"
    items = [SimpleNamespace(output_path=str(first), review_mark="ok"),
             SimpleNamespace(output_path=str(second), review_mark="ok"),
             SimpleNamespace(output_path="", review_mark="ok")]
    review = ImageReview.__new__(ImageReview)
    review.flow = SimpleNamespace(run_queue=SimpleNamespace(session=SimpleNamespace(items=items)))
    review._job = None
    saved = []
    review._save = lambda: saved.append(True)
    return review, items, saved, first, second


def test_marks_are_listed_and_set_by_file_path(tmp_path):
    review, items, saved, first, second = _review(tmp_path)
    assert review.marks_by_path() == {str(first.resolve()): "ok", str(second.resolve()): "ok"}
    review.mark_output(second, "bad_generation")
    assert items[1].review_mark == "bad_generation" and items[0].review_mark == "ok" and saved == [True]


def test_unknown_mark_or_busy_review_changes_nothing(tmp_path):
    review, items, saved, first, _second = _review(tmp_path)
    review.mark_output(first, "nonsense")
    review._job = object()
    review.mark_output(first, "bad_cutout")
    assert items[0].review_mark == "ok" and saved == []
    review._job = None
    review.mark_output(tmp_path / "other.png", "bad_cutout")
    assert saved == []
