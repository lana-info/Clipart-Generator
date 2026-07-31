from pathlib import Path

from output_naming import processed_output_path


def test_processed_output_uses_stable_name_when_overwriting():
    assert processed_output_path("out", "source.jpg", "run-1", overwrite=True) == Path("out/source_processed.png")


def test_processed_output_uses_numbered_name_when_default_collides(tmp_path):
    destination = tmp_path / "source_processed.png"
    destination.touch()
    assert processed_output_path(tmp_path, "source.jpg", "run-1", overwrite=False) == tmp_path / "source_processed_2.png"


def test_processed_output_default_does_not_require_run_stamp(tmp_path):
    assert processed_output_path(tmp_path, "source.jpg", "run-1", overwrite=False) == tmp_path / "source_processed.png"
