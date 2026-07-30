from pathlib import Path

from output_naming import processed_output_path


def test_processed_output_uses_stable_name_when_overwriting():
    assert processed_output_path("out", "source.jpg", "run-1", overwrite=True) == Path("out/source_processed.png")


def test_processed_output_keeps_run_stamp_by_default():
    assert processed_output_path("out", "source.jpg", "run-1", overwrite=False) == Path("out/source_processed_run-1.png")
