import json
from pathlib import Path
import tempfile
import unittest

from PIL import Image

from chroma_generation_record import (
    bind_generation_record, load_generation_color, record_path, write_generation_intent,
)


class GenerationRecordTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.source = Path(self.temp.name) / "source.png"

    def prepare(self, color="green"):
        intent = write_generation_intent(self.source, color=color, prompt="a flower")
        Image.new("RGB", (8, 8), (0, 255, 0)).save(self.source)
        bind_generation_record(self.source, intent)
        return intent

    def test_intent_exists_before_image_and_completed_record_is_hash_bound(self):
        intent = write_generation_intent(self.source, color="green", prompt="a flower")
        self.assertFalse(self.source.exists())
        data = json.loads(record_path(self.source, pending=True).read_text())
        self.assertEqual(data, intent)
        self.assertNotIn("prompt", data)
        self.assertIsNone(data["source_sha256"])
        Image.new("RGB", (8, 8), (0, 255, 0)).save(self.source)
        bind_generation_record(self.source, intent)
        self.assertEqual(load_generation_color(self.source), "green")
        Image.new("RGB", (8, 8), (0, 0, 255)).save(self.source)
        with self.assertRaises(ValueError):
            load_generation_color(self.source)

    def test_missing_is_legacy_but_invalid_is_not_silently_ignored(self):
        self.assertIsNone(load_generation_color(self.source))
        record_path(self.source).write_text("broken")
        with self.assertRaises(ValueError):
            load_generation_color(self.source)

    def test_pending_only_does_not_fall_back_to_global_key(self):
        write_generation_intent(self.source, color="red", prompt="flower")
        with self.assertRaises(ValueError):
            load_generation_color(self.source)

    def test_unsupported_color_and_existing_intent_fail_before_submission(self):
        with self.assertRaises(ValueError):
            write_generation_intent(self.source, color="cyan", prompt="flower")
        self.prepare()
        before = record_path(self.source, pending=True).read_bytes()
        with self.assertRaises(FileExistsError):
            write_generation_intent(self.source, color="red", prompt="other")
        self.assertEqual(before, record_path(self.source, pending=True).read_bytes())

    def test_move_together_and_separate_item_colors(self):
        self.prepare()
        other = self.source.with_name("other.png")
        intent = write_generation_intent(other, color="red", prompt="blue flower")
        Image.new("RGB", (8, 8), (255, 0, 0)).save(other)
        bind_generation_record(other, intent)
        self.assertEqual(load_generation_color(other), "red")
        moved = self.source.with_name("renamed.png")
        self.source.rename(moved)
        record_path(self.source).rename(record_path(moved))
        self.assertEqual(load_generation_color(moved), "green")

    def test_future_schema_extra_fields_and_symlink_are_rejected(self):
        self.prepare()
        path = record_path(self.source)
        original = json.loads(path.read_text())
        for change in ({"schema_version": True}, {"schema_version": 2},
                       {"quality_status": "ready"}, {"requested_color": "cyan"}):
            path.write_text(json.dumps(dict(original, **change)))
            with self.assertRaises(ValueError):
                load_generation_color(self.source)
        path.unlink()
        path.symlink_to(self.source.with_name("absent.json"))
        with self.assertRaises(ValueError):
            load_generation_color(self.source)
