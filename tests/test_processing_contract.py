import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import processing_contract

from processing_contract import (
    ProcessingContext,
    classify_failure,
    output_path,
    pipeline_steps,
    publish_atomic,
    run_workspace,
)


class ProcessingContractTests(unittest.TestCase):
    def test_plan_keeps_before_after_and_metadata_order(self):
        operations = SimpleNamespace(
            visible_mark_cleanup=False, upscale_before=True, unsharp=True,
            remove_background=True, upscale_after=True, edge_shrink=True,
            trim=True, remove_exif=True, remove_xmp=False,
            remove_iptc=False, remove_comments_text=False,
            remove_embedded_thumbnail=False, remove_generator_fields=False,
            remove_embedded_c2pa=False, export_300_dpi=True,
        )
        self.assertEqual(pipeline_steps(operations), (
            "Апскейл до удаления фона", "Unsharp Mask", "Удаление фона",
            "Апскейл после удаления фона", "Очистка края alpha", "Trim",
            "Очистка данных файла", "Экспорт 300 DPI", "Экспорт нового PNG",
        ))

    def test_cancel_and_workspace_failures_are_classified(self):
        self.assertEqual(classify_failure(RuntimeError("x"), cancelled=True).kind, "cancelled")
        self.assertEqual(classify_failure(FileNotFoundError("x")).kind, "workspace")
        self.assertNotIn("secret", classify_failure(RuntimeError("api_key=secret")).message)

    def test_atomic_publication_and_raw_output_separation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            raw = root / "raw" / "source.png"
            output = root / "output"
            raw.parent.mkdir()
            raw.write_bytes(b"image-bytes")
            target = publish_atomic(raw, output_path(raw, output))
            self.assertEqual(target.read_bytes(), raw.read_bytes())
            self.assertEqual(raw.read_bytes(), b"image-bytes")
            self.assertIsInstance(ProcessingContext(raw, root, output, {}), ProcessingContext)
            self.assertEqual(run_workspace(output), output / ".run")

    def test_non_overwrite_publication_never_replaces_a_late_collision(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            staged = root / "staged.png"
            target = root / "output" / "source_ready.png"
            staged.write_bytes(b"new result")
            target.parent.mkdir()
            target.write_bytes(b"external file created after reservation")

            with self.assertRaises(FileExistsError):
                publish_atomic(staged, target, overwrite=False)

            self.assertEqual(
                target.read_bytes(),
                b"external file created after reservation",
            )

    def test_non_overwrite_publication_survives_collision_at_final_publish(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            staged = root / "staged.png"
            target = root / "output" / "source_ready.png"
            staged.write_bytes(b"new result")
            target.parent.mkdir()
            real_replace = processing_contract.os.replace
            real_link = processing_contract.os.link
            collision_created = False

            def create_collision():
                nonlocal collision_created
                if collision_created:
                    return
                collision_created = True
                target.unlink(missing_ok=True)
                target.write_bytes(b"external file created during publication")

            def replace_with_collision(source, destination):
                if Path(destination) == target:
                    create_collision()
                return real_replace(source, destination)

            def link_with_collision(source, destination):
                if Path(destination) == target:
                    create_collision()
                return real_link(source, destination)

            with patch.object(
                processing_contract.os,
                "replace",
                side_effect=replace_with_collision,
            ), patch.object(
                processing_contract.os,
                "link",
                side_effect=link_with_collision,
            ):
                with self.assertRaises(FileExistsError):
                    publish_atomic(staged, target, overwrite=False)

            self.assertTrue(collision_created)
            self.assertEqual(
                target.read_bytes(),
                b"external file created during publication",
            )


if __name__ == "__main__":
    unittest.main()
