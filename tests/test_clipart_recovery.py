from pathlib import Path
from types import SimpleNamespace

from PIL import Image

from studio_clipart_recovery import READY_NUMBER, archived_outputs, recoverable, scan_ready_outputs


def png(path: Path):
    Image.new("RGBA", (24, 24), (200, 40, 40, 255)).save(path)
    return path


def test_ready_names_carry_the_position_in_the_set():
    assert READY_NUMBER.search("teddy_gifts_01_ready.png").group(1) == "01"
    assert READY_NUMBER.search("goose_12_ready_2.png").group(1) == "12"
    assert READY_NUMBER.search("photo.png") is None and READY_NUMBER.search("a_ready.png") is None


def test_scan_takes_the_newest_file_per_position_and_ignores_the_rest(tmp_path):
    first = png(tmp_path / "teddy_01_ready.png")
    newer = png(tmp_path / "teddy_01_ready_2.png")
    import os
    os.utime(first, (1_000, 1_000))
    os.utime(newer, (2_000, 2_000))
    png(tmp_path / "goose_02_ready.png")
    png(tmp_path / "far_99_ready.png")  # outside the set
    (tmp_path / "broken_03_ready.png").write_bytes(b"not a png at all, just text" * 5)
    (tmp_path / "note_04_ready.txt").write_text("x")
    (tmp_path / "versions").mkdir()
    png(tmp_path / "versions" / "deep_01_ready.png")
    found = scan_ready_outputs(tmp_path, 5)
    assert found == {0: newer.resolve(), 1: (tmp_path / "goose_02_ready.png").resolve()}


def test_symlinks_are_never_followed(tmp_path):
    outside = png(tmp_path / "outside.png")
    folder = tmp_path / "output"
    folder.mkdir()
    (folder / "link_01_ready.png").symlink_to(outside)
    assert scan_ready_outputs(folder, 3) == {}


def test_archive_matches_by_prompt_and_prefers_the_projects_own_record(tmp_path):
    kept = png(tmp_path / "a_01_ready.png")
    prompts = [{"id": "a"}, {"id": "b"}]
    history = [{"prompts": [{"id": "b"}, {"id": "a"}],
                "run": [{"status": "failed", "output_path": ""},
                        {"status": "succeeded", "output_path": str(kept)}]}]
    assert archived_outputs(history, prompts, tmp_path) == {0: kept.resolve()}
    assert archived_outputs([{"broken": True}, None], prompts, tmp_path) == {}


def test_recoverable_only_fills_pictures_that_are_not_done(tmp_path):
    png(tmp_path / "a_01_ready.png")
    png(tmp_path / "b_02_ready.png")
    items = [SimpleNamespace(done=True), SimpleNamespace(done=False)]
    found = recoverable(items, [{}, {}], [], tmp_path, is_done=lambda item: item.done)
    assert list(found) == [1]
    assert recoverable([SimpleNamespace(done=True)], [{}], [], tmp_path, is_done=lambda item: item.done) == {}
