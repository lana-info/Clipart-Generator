import json
from pathlib import Path
import tempfile
import unittest

from PIL import Image

from chroma_generation_record import (
    bind_generation_record, capture_generation_record, ensure_record_paths_available,
    load_generation_color, load_generation_result_kind, publish_generation_copy,
    rebind_generation_record, record_path, recover_generation_copy, write_generation_intent,
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


    def test_v2_raw_and_final_records_preserve_kind_without_rekeying_final(self):
        intent = write_generation_intent(
            self.source, color="green", prompt="flower", result_kind="clipart"
        )
        Image.new("RGB", (8, 8), (0, 255, 0)).save(self.source)
        bind_generation_record(self.source, intent, stage="raw")
        self.assertEqual(load_generation_color(self.source), "green")
        self.assertEqual(load_generation_result_kind(self.source), "clipart")

        final = self.source.with_name("result.png")
        Image.new("RGBA", (8, 8), (10, 20, 30, 0)).save(final)
        bind_generation_record(final, intent, stage="final")
        self.assertIsNone(load_generation_color(final))
        self.assertEqual(load_generation_result_kind(final), "clipart")
        data = json.loads(record_path(final).read_text())
        self.assertEqual(data["stage"], "final")
        self.assertNotIn("prompt", data)

    def test_v2_surface_intent_allows_no_chroma_color_and_is_hash_bound(self):
        intent = write_generation_intent(
            self.source, color=None, prompt="pattern", result_kind="pattern"
        )
        self.assertIsNone(intent["requested_color"])
        Image.new("RGB", (8, 8), (30, 40, 50)).save(self.source)
        bind_generation_record(self.source, intent, stage="raw")
        self.assertIsNone(load_generation_color(self.source))
        self.assertEqual(load_generation_result_kind(self.source), "pattern")
        Image.new("RGB", (8, 8), (1, 2, 3)).save(self.source)
        with self.assertRaises(ValueError):
            load_generation_result_kind(self.source)

    def test_legacy_v1_record_keeps_color_but_does_not_invent_result_kind(self):
        # Existing installs may already have schema-v1 records.
        self.prepare("red")
        path = record_path(self.source)
        data = json.loads(path.read_text())
        # prepare() should continue producing/reading a compatible record; rewrite a literal v1 fixture.
        legacy = {
            "schema_version": 1,
            "requested_color": "red",
            "prompt_sha256": data["prompt_sha256"],
            "source_sha256": data["source_sha256"],
        }
        path.write_text(json.dumps(legacy))
        self.assertEqual(load_generation_color(self.source), "red")
        self.assertIsNone(load_generation_result_kind(self.source))

    def test_rebind_after_local_edit_preserves_v2_kind_and_updates_hash(self):
        intent = write_generation_intent(
            self.source, color="green", prompt="flower", result_kind="clipart"
        )
        Image.new("RGBA", (8, 8), (10, 20, 30, 128)).save(self.source)
        bind_generation_record(self.source, intent, stage="final")
        captured = capture_generation_record(self.source)
        self.assertEqual(captured["result_kind"], "clipart")

        Image.new("RGBA", (8, 8), (10, 20, 30, 255)).save(self.source)
        with self.assertRaises(ValueError):
            load_generation_result_kind(self.source)
        rebind_generation_record(self.source, captured, stage="final")
        self.assertEqual(load_generation_result_kind(self.source), "clipart")
        self.assertIsNone(load_generation_color(self.source))

    def test_rebind_can_attach_captured_kind_to_separate_copy(self):
        intent = write_generation_intent(
            self.source, color=None, prompt="pattern", result_kind="pattern"
        )
        Image.new("RGB", (8, 8), (1, 2, 3)).save(self.source)
        bind_generation_record(self.source, intent, stage="final")
        captured = capture_generation_record(self.source)
        copy = self.source.with_name("copy.png")
        Image.new("RGB", (8, 8), (4, 5, 6)).save(copy)

        rebind_generation_record(copy, captured, stage="final", overwrite=False)
        self.assertEqual(load_generation_result_kind(copy), "pattern")
        self.assertIsNone(load_generation_color(copy))

    def test_capture_does_not_invent_kind_for_legacy_v1(self):
        self.prepare("green")
        path = record_path(self.source)
        data = json.loads(path.read_text())
        legacy = {
            "schema_version": 1,
            "requested_color": "green",
            "prompt_sha256": data["prompt_sha256"],
            "source_sha256": data["source_sha256"],
        }
        path.write_text(json.dumps(legacy))
        self.assertIsNone(capture_generation_record(self.source))

    def test_record_path_preflight_rejects_raw_or_final_pending_or_completed_collision(self):
        final = self.source.with_name("final.png")
        for image_path in (self.source, final):
            for pending in (False, True):
                with self.subTest(image=image_path.name, pending=pending):
                    target = record_path(image_path, pending=pending)
                    target.write_text("occupied")
                    with self.assertRaises(FileExistsError):
                        ensure_record_paths_available(self.source, final)
                    target.unlink()
        ensure_record_paths_available(self.source, final)


    def test_recover_generation_copy_removes_matching_partial_publish_after_crash(self):
        from unittest.mock import patch
        import chroma_generation_record as records

        intent = write_generation_intent(
            self.source, color="green", prompt="flower", result_kind="clipart"
        )
        Image.new("RGBA", (8, 8), (1, 2, 3, 0)).save(self.source)
        bind_generation_record(self.source, intent, stage="final")
        captured = capture_generation_record(self.source)
        staged = self.source.with_name("staged.png")
        Image.new("RGBA", (8, 8), (9, 8, 7, 0)).save(staged)
        destination = self.source.with_name("copy.png")
        original_publish = records.publish_atomic

        def crash_on_sidecar(source, target, *, overwrite=False):
            if Path(target) == record_path(destination):
                raise SystemExit("simulated crash")
            return original_publish(source, target, overwrite=overwrite)

        with patch("chroma_generation_record.publish_atomic", side_effect=crash_on_sidecar):
            with self.assertRaises(SystemExit):
                publish_generation_copy(staged, destination, captured)

        self.assertTrue(destination.exists())
        self.assertFalse(record_path(destination).exists())
        self.assertTrue(recover_generation_copy(destination))
        self.assertFalse(destination.exists())
        self.assertFalse(record_path(destination).exists())

    def test_rebind_refuses_when_cooperative_record_lock_is_held(self):
        intent = write_generation_intent(
            self.source, color="green", prompt="flower", result_kind="clipart"
        )
        Image.new("RGBA", (8, 8), (1, 2, 3, 0)).save(self.source)
        bind_generation_record(self.source, intent, stage="final")
        captured = capture_generation_record(self.source)
        sidecar = record_path(self.source)
        before = sidecar.read_bytes()
        lock = sidecar.with_name(sidecar.name + ".lock")
        lock.write_text("held")
        Image.new("RGBA", (8, 8), (9, 8, 7, 0)).save(self.source)
        try:
            with self.assertRaises(ValueError):
                rebind_generation_record(self.source, captured, stage="final")
        finally:
            lock.unlink(missing_ok=True)
        self.assertEqual(sidecar.read_bytes(), before)

    def test_future_schema_extra_fields_and_symlink_are_rejected(self):
        self.prepare()
        path = record_path(self.source)
        original = json.loads(path.read_text())
        for change in ({"schema_version": True}, {"schema_version": 3},
                       {"quality_status": "ready"}, {"requested_color": "cyan"}):
            path.write_text(json.dumps(dict(original, **change)))
            with self.assertRaises(ValueError):
                load_generation_color(self.source)
        path.unlink()
        path.symlink_to(self.source.with_name("absent.json"))
        with self.assertRaises(ValueError):
            load_generation_color(self.source)
