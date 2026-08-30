from pathlib import Path
import tempfile
import unittest

from output_naming import (
    BatchOutputNameReservation,
    generated_output_path,
    processed_output_path,
    workspace_layout,
)


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


def test_generated_output_uses_short_ready_name_and_collision_number(tmp_path):
    assert generated_output_path(tmp_path, 1, "Blue watercolor flowers") == tmp_path / "blue_watercolor_flowers_01_ready.png"
    (tmp_path / "blue_watercolor_flowers_01_ready.png").touch()
    assert generated_output_path(tmp_path, 1, "Blue watercolor flowers") == tmp_path / "blue_watercolor_flowers_01_ready_2.png"


class GeneratedOutputNameTests(unittest.TestCase):
    def test_uses_only_the_object_name_without_prompt_labels(self):
        with tempfile.TemporaryDirectory() as directory:
            prompt = "Object: fox. Scene: spring garden. Style: watercolor."
            self.assertEqual(
                generated_output_path(directory, 1, prompt),
                Path(directory) / "fox_01_ready.png",
            )

    def test_translates_common_russian_subject_names_to_english(self):
        with tempfile.TemporaryDirectory() as directory:
            prompt = "Объект: лисёнок. Сцена: весенний сад. Стиль: акварель."
            self.assertEqual(
                generated_output_path(directory, 1, prompt),
                Path(directory) / "fox_01_ready.png",
            )

    def test_keeps_a_short_free_form_english_subject(self):
        with tempfile.TemporaryDirectory() as directory:
            self.assertEqual(
                generated_output_path(directory, 2, "Teddy bear with a ribbon, isolated clipart"),
                Path(directory) / "teddy_bear_with_02_ready.png",
            )


def test_generated_output_falls_back_without_manual_filename(tmp_path):
    assert generated_output_path(tmp_path, 3, "!!!") == tmp_path / "clipart_03_ready.png"


def test_batch_reservation_prevents_processing_name_collisions(tmp_path):
    (tmp_path / "same_ready.png").touch()
    reservation = BatchOutputNameReservation(tmp_path)

    first = reservation.reserve_processed("one/same.jpg", overwrite=False)
    second = reservation.reserve_processed("two/same.png", overwrite=False)

    assert first == tmp_path / "same_ready_2.png"
    assert second == tmp_path / "same_ready_3.png"


def test_batch_reservation_never_reuses_overwrite_destination(tmp_path):
    reservation = BatchOutputNameReservation(tmp_path)

    first = reservation.reserve_processed("one/same.jpg", overwrite=True)
    second = reservation.reserve_processed("two/same.png", overwrite=True)

    assert first == tmp_path / "same_ready.png"
    assert second == tmp_path / "same_ready_2.png"
