from pathlib import Path

from output_naming import processed_output_path, workspace_layout


def test_processed_output_uses_stable_name_when_overwriting():
    assert processed_output_path("out", "source.jpg", "run-1", overwrite=True) == Path("out/source_ready.png")


def test_processed_output_uses_numbered_name_when_default_collides(tmp_path):
    destination = tmp_path / "source_ready.png"
    destination.touch()
    assert processed_output_path(tmp_path, "source.jpg", "run-1", overwrite=False) == tmp_path / "source_ready_2.png"


def test_processed_output_default_does_not_require_run_stamp(tmp_path):
    assert processed_output_path(tmp_path, "source.jpg", "run-1", overwrite=False) == tmp_path / "source_ready.png"


def test_workspace_layout_migrates_legacy_output_path_to_parent(tmp_path):
    layout = workspace_layout(tmp_path / "output")
    assert layout.root == tmp_path
    assert layout.output == tmp_path / "output"
    assert layout.rough == tmp_path / "rough"
    assert layout.transient == tmp_path / ".run"
