import errno
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from PIL import Image
from PyQt6.QtCore import QEvent, Qt
from PyQt6.QtGui import QKeyEvent
from PyQt6.QtWidgets import QApplication, QMessageBox, QPushButton
from v3_components import ButtonVariant

from v3_transparency_preview import (
    MAX_EDITOR_IMAGE_PIXELS,
    ClipartTransparencyEditorPage,
    ClipartTransparencyPreview,
    MaskEditDocument,
    MaskSaveFallbackNotice,
    TransparencyCanvas,
)


class TransparencyPreviewWidgetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_widget_exposes_approved_background_choices(self):
        widget = ClipartTransparencyPreview()

        self.assertEqual(widget.background_combo.count(), 6)
        self.assertEqual(widget.background_combo.currentText(), "Шахматный")
        self.assertTrue(widget.preview.pixmap().isNull())

    def test_widget_renders_image_and_reacts_to_background_change(self):
        widget = ClipartTransparencyPreview()
        widget.resize(420, 320)
        widget.set_image(Image.new("RGBA", (20, 20), (10, 20, 30, 128)))
        first = widget.preview.pixmap().toImage().pixel(0, 0)

        widget.background_combo.setCurrentText("Ярко-розовый")
        second = widget.preview.pixmap().toImage().pixel(0, 0)

        self.assertFalse(widget.preview.pixmap().isNull())
        self.assertNotEqual(first, second)

    def test_brush_changes_mask_and_reset_restores_source_alpha(self):
        widget = ClipartTransparencyPreview()
        widget.set_image(Image.new("RGBA", (20, 20), (10, 20, 30, 255)))
        widget.action_combo.setCurrentText("Стереть область")
        widget.radius_spin.setValue(2)

        widget.apply_stroke((10, 10))

        self.assertEqual(widget._mask.getpixel((10, 10)), 0)
        widget.reset_button.click()
        self.assertEqual(widget._mask.getpixel((10, 10)), 255)

    def test_corrected_png_keeps_rgb_and_can_save_mask_separately(self):
        widget = ClipartTransparencyPreview()
        widget.set_image(Image.new("RGBA", (4, 4), (10, 20, 30, 255)))
        widget.action_combo.setCurrentText("Стереть область")
        widget.radius_spin.setValue(1)
        widget.apply_stroke((2, 2))

        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "corrected.png"
            mask = Path(directory) / "corrected-mask.png"
            widget.save_corrected_png(output)
            widget.save_mask(mask)
            with Image.open(output) as image:
                self.assertEqual(image.getpixel((0, 0)), (10, 20, 30, 255))
                self.assertEqual(image.getpixel((2, 2))[-1], 0)
            with Image.open(mask) as saved_mask:
                self.assertEqual(saved_mask.mode, "L")
                self.assertEqual(saved_mask.getpixel((2, 2)), 0)

    def test_document_groups_a_continuous_stroke_into_one_undo_step(self):
        document = MaskEditDocument(
            Image.new("RGBA", (40, 20), (10, 20, 30, 255))
        )

        document.begin_stroke()
        document.extend_stroke(
            ((5, 10), (35, 10)),
            radius=2,
            action="remove",
            hardness=100,
        )
        document.end_stroke()

        self.assertEqual(document.mask.getpixel((20, 10)), 0)
        self.assertTrue(document.can_undo)
        document.undo()
        self.assertEqual(document.mask.getpixel((20, 10)), 255)
        self.assertTrue(document.can_redo)
        document.redo()
        self.assertEqual(document.mask.getpixel((20, 10)), 0)

    def test_document_reset_and_save_write_corrected_png_and_automatic_mask(self):
        document = MaskEditDocument(
            Image.new("RGBA", (12, 12), (7, 8, 9, 255))
        )
        document.begin_stroke()
        document.extend_stroke(
            ((6, 6),),
            radius=2,
            action="remove",
            hardness=75,
        )
        document.end_stroke()

        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "output" / "flowers_ready.png"
            mask = Path(directory) / "rough" / "flowers_ready_alpha-mask.png"
            document.save(output, mask)

            with Image.open(output) as corrected:
                self.assertEqual(corrected.getpixel((0, 0))[:3], (7, 8, 9))
                self.assertEqual(corrected.getpixel((6, 6))[-1], 0)
            with Image.open(mask) as saved_mask:
                self.assertEqual(saved_mask.mode, "L")
                self.assertEqual(saved_mask.getpixel((6, 6)), 0)

        document.reset()
        self.assertEqual(document.mask.getextrema(), (255, 255))

    def test_document_save_rebinds_hash_bound_result_kind_sidecar(self):
        from chroma_generation_record import (
            bind_generation_record, load_generation_result_kind, write_generation_intent,
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / "output" / "flowers_ready.png"
            mask = root / "rough" / "flowers_ready_alpha-mask.png"
            output.parent.mkdir()
            Image.new("RGBA", (12, 12), (7, 8, 9, 255)).save(output)
            intent = write_generation_intent(
                output, color="green", prompt="flower", result_kind="clipart"
            )
            bind_generation_record(output, intent, stage="final")
            with Image.open(output) as opened:
                document = MaskEditDocument(opened.convert("RGBA"))
            document.begin_stroke()
            document.extend_stroke(((6, 6),), radius=2, action="remove", hardness=100)
            document.end_stroke()

            document.save(output, mask)

            self.assertEqual(load_generation_result_kind(output), "clipart")


    def test_document_save_rolls_png_mask_and_sidecar_back_when_sidecar_commit_fails(self):
        from chroma_generation_record import (
            bind_generation_record, record_path, write_generation_intent,
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / "output" / "ready.png"
            mask = root / "rough" / "ready-alpha-mask.png"
            output.parent.mkdir(); mask.parent.mkdir()
            Image.new("RGBA", (8, 8), (1, 2, 3, 255)).save(output)
            Image.new("L", (8, 8), 255).save(mask)
            intent = write_generation_intent(
                output, color="green", prompt="flower", result_kind="clipart"
            )
            bind_generation_record(output, intent, stage="final")
            sidecar = record_path(output)
            before_png = output.read_bytes()
            before_mask = mask.read_bytes()
            before_sidecar = sidecar.read_bytes()
            with Image.open(output) as opened:
                document = MaskEditDocument(opened.convert("RGBA"))
            document.begin_stroke()
            document.extend_stroke(((4, 4),), radius=2, action="remove", hardness=100)
            document.end_stroke()
            original_replace = os.replace

            def fail_sidecar_commit(source, destination):
                if Path(destination) == sidecar and str(source).endswith(".tmp"):
                    raise OSError("sidecar commit failed")
                return original_replace(source, destination)

            with patch("v3_transparency_preview.os.replace", side_effect=fail_sidecar_commit):
                with self.assertRaises(OSError):
                    document.save(output, mask)

            self.assertEqual(output.read_bytes(), before_png)
            self.assertEqual(mask.read_bytes(), before_mask)
            self.assertEqual(sidecar.read_bytes(), before_sidecar)

    def test_document_save_preserves_png_dpi(self):
        source = Image.new("RGBA", (12, 12), (7, 8, 9, 255))
        source.info["dpi"] = (300.0, 300.0)
        document = MaskEditDocument(source)

        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "output" / "flowers_ready.png"
            mask = Path(directory) / "rough" / "flowers_ready_alpha-mask.png"
            document.save(output, mask)

            with Image.open(output) as corrected:
                self.assertAlmostEqual(corrected.info["dpi"][0], 300, delta=1)
                self.assertAlmostEqual(corrected.info["dpi"][1], 300, delta=1)

    def test_document_save_rolls_both_files_back_when_pair_commit_fails(self):
        document = MaskEditDocument(
            Image.new("RGBA", (12, 12), (7, 8, 9, 128))
        )
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "output" / "ready.png"
            mask = Path(directory) / "rough" / "ready_alpha-mask.png"
            output.parent.mkdir()
            mask.parent.mkdir()
            Image.new("RGBA", (4, 4), (1, 2, 3, 255)).save(output)
            Image.new("L", (4, 4), 77).save(mask)
            original_replace = os.replace

            def fail_mask_commit(source, destination):
                if Path(destination) == mask and str(source).endswith(".tmp"):
                    raise OSError("simulated commit failure")
                return original_replace(source, destination)

            with patch("v3_transparency_preview.os.replace", side_effect=fail_mask_commit):
                with self.assertRaises(OSError):
                    document.save(output, mask)

            with Image.open(output) as restored_output:
                self.assertEqual(restored_output.size, (4, 4))
            with Image.open(mask) as restored_mask:
                self.assertEqual(restored_mask.getpixel((0, 0)), 77)

    def test_next_start_recovers_pair_after_process_stops_mid_commit(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / "output" / "ready.png"
            mask = root / "rough" / "ready_alpha-mask.png"
            output.parent.mkdir()
            mask.parent.mkdir()
            Image.new("RGBA", (4, 4), (1, 2, 3, 255)).save(output)
            Image.new("L", (4, 4), 77).save(mask)
            marker, backups = MaskEditDocument._pair_transaction_paths(output, mask)
            MaskEditDocument._write_pair_transaction(
                marker,
                phase="prepared",
                existed=(True, True),
            )
            os.replace(output, backups[0])
            os.replace(mask, backups[1])
            Image.new("RGBA", (8, 8), (200, 0, 0, 255)).save(output)

            recovered = MaskEditDocument.recover_pair(output, mask)

            self.assertTrue(recovered)
            with Image.open(output) as restored_output:
                self.assertEqual(restored_output.size, (4, 4))
                self.assertEqual(restored_output.getpixel((0, 0)), (1, 2, 3, 255))
            with Image.open(mask) as restored_mask:
                self.assertEqual(restored_mask.getpixel((0, 0)), 77)
            self.assertFalse(marker.exists())
            self.assertFalse(any(backup.exists() for backup in backups))


    def test_next_start_recovers_png_mask_and_sidecar_v2_transaction(self):
        from chroma_generation_record import bind_generation_record, record_path, write_generation_intent
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / "output" / "ready.png"
            mask = root / "rough" / "ready-alpha-mask.png"
            output.parent.mkdir(); mask.parent.mkdir()
            Image.new("RGBA", (4, 4), (1, 2, 3, 255)).save(output)
            Image.new("L", (4, 4), 77).save(mask)
            intent = write_generation_intent(output, color="green", prompt="flower", result_kind="clipart")
            bind_generation_record(output, intent, stage="final")
            sidecar = record_path(output)
            old_png, old_mask, old_sidecar = output.read_bytes(), mask.read_bytes(), sidecar.read_bytes()
            marker, backups = MaskEditDocument._pair_transaction_paths(output, mask)
            identity = marker.stem.rsplit("-", 1)[-1]
            sidecar_backup = sidecar.with_name(f".{sidecar.name}.{identity}.backup")
            MaskEditDocument._write_pair_transaction(
                marker, phase="prepared", existed=(True, True, True), includes_sidecar=True
            )
            os.replace(output, backups[0]); os.replace(mask, backups[1]); os.replace(sidecar, sidecar_backup)
            Image.new("RGBA", (8, 8), (200, 0, 0, 255)).save(output)
            Image.new("L", (8, 8), 0).save(mask)
            sidecar.write_text("new-but-uncommitted")

            self.assertTrue(MaskEditDocument.recover_pair(output, mask))

            self.assertEqual(output.read_bytes(), old_png)
            self.assertEqual(mask.read_bytes(), old_mask)
            self.assertEqual(sidecar.read_bytes(), old_sidecar)
            self.assertFalse(marker.exists())
            self.assertFalse(backups[0].exists() or backups[1].exists() or sidecar_backup.exists())


    def test_document_save_refuses_concurrent_generation_transaction_without_lost_update(self):
        from chroma_generation_record import (
            bind_generation_record, generation_transaction_lock, record_path,
            write_generation_intent,
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / "output" / "ready.png"
            mask = root / "rough" / "ready_alpha-mask.png"
            output.parent.mkdir(); mask.parent.mkdir()
            Image.new("RGBA", (12, 12), (1, 2, 3, 255)).save(output)
            Image.new("L", (12, 12), 255).save(mask)
            intent = write_generation_intent(
                output, color="green", prompt="flower", result_kind="clipart"
            )
            bind_generation_record(output, intent, stage="final")
            before = (output.read_bytes(), mask.read_bytes(), record_path(output).read_bytes())
            document = MaskEditDocument(Image.new("RGBA", (12, 12), (9, 8, 7, 255)))

            with generation_transaction_lock(output):
                with self.assertRaises(ValueError):
                    document.save(output, mask)

            self.assertEqual(output.read_bytes(), before[0])
            self.assertEqual(mask.read_bytes(), before[1])
            self.assertEqual(record_path(output).read_bytes(), before[2])

    def test_pair_recovery_without_marker_does_not_create_generation_lock_file(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / "ready.png"
            mask = root / "ready-mask.png"
            lock = output.with_name(output.name + ".generation.json.lock")
            self.assertFalse(MaskEditDocument.recover_pair(output, mask))
            self.assertFalse(lock.exists())

    def test_document_history_is_bounded_by_memory_not_only_step_count(self):
        document = MaskEditDocument(
            Image.new("RGBA", (512, 512), (10, 20, 30, 255))
        )
        document.HISTORY_MEMORY_LIMIT = 1024 * 1024

        for index in range(12):
            document.begin_stroke()
            document.extend_stroke(
                ((256, 256),),
                radius=400,
                action="remove" if index % 2 == 0 else "add",
                hardness=100,
            )
            document.end_stroke()

        self.assertLessEqual(
            document.history_bytes,
            document.HISTORY_MEMORY_LIMIT,
        )

    def test_editor_uses_the_approved_compact_controls_and_scrollable_files(self):
        page = ClipartTransparencyEditorPage()
        button_texts = {
            button.text() for button in page.findChildren(QPushButton)
        }

        self.assertEqual(
            page.title_label.text(),
            "Проверка и корректировка прозрачности",
        )
        self.assertEqual(set(page.zoom_buttons), {"fit", 50, 100, 150, 200, 300})
        self.assertNotIn("25%", button_texts)
        self.assertNotIn("Alpha-маска", button_texts)
        self.assertIn("Сохранить PNG", button_texts)
        self.assertIn("К результатам", button_texts)
        self.assertIs(page.save_button.variant, ButtonVariant.PRIMARY)
        self.assertIs(page.back_button.variant, ButtonVariant.SECONDARY)
        self.assertEqual(
            page.file_list.verticalScrollBarPolicy(),
            Qt.ScrollBarPolicy.ScrollBarAsNeeded,
        )
        self.assertTrue(page.canvas.space_pan_enabled)
        self.assertEqual(page.brush_diameter, 16)
        self.assertEqual(page.canvas.brush_hardness, 100)
        self.assertTrue(page.brush_style_buttons[100].isChecked())
        page._hardness_changed(0)
        self.assertEqual(page.canvas.brush_hardness, 0)
        self.assertTrue(page.brush_style_buttons[0].isChecked())
        self.assertEqual(page.canvas.brush_action, "remove")
        page.deleteLater()

    def test_space_temporarily_enables_pan_and_hand_indicator_from_editor_controls(self):
        page = ClipartTransparencyEditorPage()

        QApplication.sendEvent(
            page.diameter_slider,
            QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Space, Qt.KeyboardModifier.NoModifier),
        )
        self.assertTrue(page.canvas.space_pan_indicator_visible)

        QApplication.sendEvent(
            page.diameter_slider,
            QKeyEvent(QEvent.Type.KeyRelease, Qt.Key.Key_Space, Qt.KeyboardModifier.NoModifier),
        )
        self.assertFalse(page.canvas.space_pan_indicator_visible)
        page.deleteLater()

    def test_editor_switches_files_and_saves_mask_automatically_with_png(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = root / "output" / "flowers_ready.png"
            second = root / "output" / "leaves_ready.png"
            first.parent.mkdir(parents=True)
            Image.new("RGBA", (16, 16), (10, 20, 30, 255)).save(first)
            Image.new("RGBA", (16, 16), (40, 50, 60, 255)).save(second)
            page = ClipartTransparencyEditorPage()
            page.set_files((first, second), selected_index=1, rough_dir=root / "rough")

            self.assertEqual(page.file_list.count(), 2)
            self.assertEqual(page.current_path, second)
            page.document.begin_stroke()
            page.document.extend_stroke(
                ((8, 8),), radius=2, action="remove", hardness=100
            )
            page.document.end_stroke()
            page.save_current()

            automatic_mask = root / "rough" / "leaves_ready_alpha-mask.png"
            self.assertTrue(automatic_mask.is_file())
            with Image.open(second) as corrected:
                self.assertEqual(corrected.getpixel((8, 8))[-1], 0)
            page.deleteLater()

    def test_editor_loads_only_the_selected_file_thumbnail(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "output"
            first = root / "flowers_ready.png"
            second = root / "leaves_ready.png"
            root.mkdir(parents=True)
            Image.new("RGBA", (16, 16), (10, 20, 30, 255)).save(first)
            Image.new("RGBA", (16, 16), (40, 50, 60, 255)).save(second)
            page = ClipartTransparencyEditorPage()

            page.set_files((first, second), selected_index=0)

            self.assertEqual(page.current_path, first)
            self.assertEqual(page.document.image.size, (16, 16))
            self.assertFalse(page.file_list.item(0).icon().isNull())
            self.assertTrue(page.file_list.item(1).icon().isNull())

            page.file_list.setCurrentRow(1)

            self.assertFalse(page.file_list.item(1).icon().isNull())
            page.deleteLater()

    def test_editor_keeps_selected_zoom_when_switching_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            paths = []
            for name in ("one.png", "two.png"):
                path = root / name
                Image.new("RGBA", (16, 16), (10, 20, 30, 255)).save(path)
                paths.append(path)
            page = ClipartTransparencyEditorPage()
            page.set_files(paths)
            page.zoom_buttons[300].click()

            page.file_list.setCurrentRow(1)

            self.assertEqual(page.canvas.zoom_percent, 300)
            self.assertTrue(page.zoom_buttons[300].isChecked())
            page.deleteLater()

    def test_editor_offers_only_the_approved_zoom_presets(self):
        page = ClipartTransparencyEditorPage()

        self.assertEqual(
            list(page.zoom_buttons),
            ["fit", 50, 100, 150, 200, 300],
        )
        self.assertEqual(
            [button.text() for button in page.zoom_buttons.values()],
            ["Fit", "50%", "100%", "150%", "200%", "300%"],
        )
        page.deleteLater()

    def test_editor_reports_save_errors_instead_of_ignoring_them(self):
        page = ClipartTransparencyEditorPage()
        with patch.object(page, "save_current", side_effect=OSError("disk full")):
            with patch("v3_transparency_preview.QMessageBox.critical") as critical:
                page._save_clicked()

        critical.assert_called_once()
        page.deleteLater()

    def test_editor_rejects_an_oversized_image_before_decoding_it(self):
        page = ClipartTransparencyEditorPage()
        page._paths = [Path("oversized.png")]
        page.file_list.addItem("oversized.png")
        source = MagicMock()
        source.__enter__.return_value = source
        source.__exit__.return_value = False
        source.size = (MAX_EDITOR_IMAGE_PIXELS + 1, 1)

        with patch("v3_transparency_preview.Image.open", return_value=source):
            with patch("v3_transparency_preview.QMessageBox.warning") as warning:
                page._select_file(0)

        source.copy.assert_not_called()
        warning.assert_called_once()
        self.assertIn("слишком большое", warning.call_args.args[2].casefold())
        self.assertIn("40", warning.call_args.args[2])
        page.deleteLater()

    def test_canvas_does_not_join_a_stroke_across_the_outside_of_image(self):
        document = MaskEditDocument(
            Image.new("RGBA", (100, 60), (10, 20, 30, 255))
        )
        canvas = TransparencyCanvas()
        canvas.set_document(document)
        canvas.brush_radius = 2
        canvas.brush_action = "remove"
        canvas.brush_hardness = 100
        document.begin_stroke()
        canvas._last_image_point = (5, 30)

        canvas._extend_active_stroke(None)
        canvas._extend_active_stroke((95, 30))
        document.end_stroke()

        self.assertEqual(document.mask.getpixel((50, 30)), 255)
        self.assertEqual(document.mask.getpixel((95, 30)), 0)
        canvas.deleteLater()

    def test_editor_warns_before_discarding_unsaved_mask_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "ready.png"
            Image.new("RGBA", (16, 16), (10, 20, 30, 255)).save(path)
            page = ClipartTransparencyEditorPage()
            page.set_files((path,))
            page.document.begin_stroke()
            page.document.extend_stroke(
                ((8, 8),), radius=2, action="remove", hardness=100
            )
            page.document.end_stroke()
            requested = []
            page.back_requested.connect(lambda: requested.append(True))

            with patch(
                "v3_transparency_preview.QMessageBox.exec",
                return_value=QMessageBox.StandardButton.Cancel,
            ):
                page._back_clicked()
            self.assertEqual(requested, [])

            with patch(
                "v3_transparency_preview.QMessageBox.exec",
                return_value=QMessageBox.StandardButton.Discard,
            ):
                page._back_clicked()
            self.assertEqual(requested, [True])
            page.deleteLater()

    def test_back_after_pen_apply_and_save_asks_nothing_and_buttons_are_russian(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "ready.png"
            Image.new("RGBA", (16, 16), (10, 20, 30, 255)).save(path)
            page = ClipartTransparencyEditorPage()
            page.set_files((path,))
            stale = __import__("v3_transparency_preview").InlineContour()
            stale.add_point((1, 1))  # draft left behind by an undo before the contour was applied
            page._draft_contours[path] = stale
            requested = []
            page.back_requested.connect(lambda: requested.append(True))
            with patch("v3_transparency_preview.QMessageBox.exec") as ask:
                page._back_clicked()
            ask.assert_not_called()
            self.assertEqual(requested, [True])

            page.document.begin_stroke()
            page.document.extend_stroke(((8, 8),), radius=2, action="remove", hardness=100)
            page.document.end_stroke()
            seen = []

            def record(box):
                seen.extend(b.text() for b in box.buttons())
                return QMessageBox.StandardButton.Cancel

            with patch.object(QMessageBox, "exec", record):
                page._back_clicked()
            self.assertEqual(sorted(seen), ["Не сохранять", "Остаться"])
            page.deleteLater()


class MaskSaveBusyOutcomeTests(unittest.TestCase):
    """Owner 2026-10-30 (Windows): the ready PNG can be held open by a viewer
    or Explorer thumbnails (WinError 32/«используется другим процессом»).

    Invariant under test: every save outcome is explicit — target written and
    dirty reset, timestamped copy with a notice, or a loud error. No silent
    saves, no lost edits, no leftover .tmp files.
    """

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def _dirty_document(self) -> MaskEditDocument:
        document = MaskEditDocument(Image.new("RGBA", (12, 12), (7, 8, 9, 255)))
        document.begin_stroke()
        document.extend_stroke(((6, 6),), radius=2, action="remove", hardness=100)
        document.end_stroke()
        return document

    def _pair_paths(self, root: Path, pre_existing: bool = True) -> tuple[Path, Path]:
        output = root / "output" / "flowers_ready.png"
        mask = root / "rough" / "flowers_ready_alpha-mask.png"
        output.parent.mkdir(parents=True)
        mask.parent.mkdir(parents=True)
        if pre_existing:
            Image.new("RGBA", (12, 12), (7, 8, 9, 255)).save(output)
            Image.new("L", (12, 12), 255).save(mask)
        return output, mask

    @staticmethod
    def _new_editor_page(root: Path) -> tuple[ClipartTransparencyEditorPage, Path]:
        (root / "output").mkdir(parents=True)
        (root / "rough").mkdir(parents=True)
        target = root / "output" / "flowers_ready.png"
        Image.new("RGBA", (12, 12), (7, 8, 9, 255)).save(target)
        page = ClipartTransparencyEditorPage()
        page.set_files((target,), rough_dir=root / "rough")
        page.document.begin_stroke()
        page.document.extend_stroke(((6, 6),), radius=2, action="remove", hardness=100)
        page.document.end_stroke()
        return page, target

    @staticmethod
    def _leftovers(root: Path) -> list[Path]:
        return [
            path for path in root.rglob("*")
            if path.is_file() and (
                path.name.endswith(".tmp")
                or ".backup" in path.name
                or (path.name.startswith(".vibix-pair-") and path.suffix == ".json")
            )
        ]

    @staticmethod
    def _busy_replace(busy_targets: set[Path] | None = None, limit: int | None = None):
        """Patch os.replace: tmp->busy_target fails like a Windows sharing violation."""
        original_replace = os.replace
        hits: list[Path] = []

        def replace(source, destination):  # type: ignore[no-untyped-def]
            source_path, destination_path = Path(source), Path(destination)
            if (
                source_path.suffix == ".tmp"
                and (busy_targets is None or destination_path in busy_targets)
                and (limit is None or len(hits) < limit)
            ):
                hits.append(destination_path)
                raise PermissionError(errno.EACCES, "simulated sharing violation")
            return original_replace(source, destination)

        return replace, hits

    def test_busy_classifier_flags_windows_and_posix_busy_errors(self):
        from v3_transparency_preview import _is_target_busy_error

        self.assertTrue(_is_target_busy_error(PermissionError(errno.EACCES, "busy")))
        self.assertTrue(_is_target_busy_error(PermissionError(errno.EPERM, "busy")))
        self.assertTrue(_is_target_busy_error(OSError(errno.EBUSY, "busy")))
        self.assertFalse(_is_target_busy_error(OSError(errno.EIO, "disk failure")))
        self.assertFalse(_is_target_busy_error(ValueError("unrelated")))

    def test_document_save_retries_busy_target_and_writes_it(self):
        document = self._dirty_document()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output, mask = self._pair_paths(root)
            before = output.read_bytes()
            replace, hits = self._busy_replace(busy_targets={output}, limit=1)
            sleeps: list[float] = []

            with patch("v3_transparency_preview.os.replace", side_effect=replace), patch(
                "v3_transparency_preview.time.sleep", side_effect=sleeps.append
            ):
                document.save(output, mask)

            self.assertEqual(len(hits), 1, "transient lock: one retry must be enough")
            self.assertEqual(sleeps, [0.3], "retry pause ~0.3s, total well below 1s")
            self.assertFalse(document.is_dirty)
            with Image.open(output) as corrected:
                self.assertEqual(corrected.getpixel((6, 6))[-1], 0)
            self.assertNotEqual(output.read_bytes(), before)
            with Image.open(mask) as saved_mask:
                self.assertEqual(saved_mask.getpixel((6, 6)), 0)
            self.assertEqual(self._leftovers(root), [])

    def test_document_save_persistent_busy_commits_timestamped_copy_with_notice(self):
        document = self._dirty_document()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output, mask = self._pair_paths(root)
            before_output = output.read_bytes()
            before_mask = mask.read_bytes()
            replace, hits = self._busy_replace(busy_targets={output})
            sleeps: list[float] = []

            with patch("v3_transparency_preview.os.replace", side_effect=replace), patch(
                "v3_transparency_preview.time.sleep", side_effect=sleeps.append
            ):
                with self.assertRaises(MaskSaveFallbackNotice) as raised:
                    document.save(output, mask)

            notice = raised.exception
            self.assertEqual(len(hits), 3, "initial attempt + two short retries")
            self.assertEqual(sleeps, [0.3, 0.4])
            self.assertLessEqual(sum(sleeps), 1.0)
            self.assertEqual(notice.target_path, output)
            self.assertEqual(
                notice.output_path.parent, output.parent, "copy stays near the target"
            )
            self.assertRegex(notice.output_path.name, r"flowers_ready_saved_\d{8}_\d{6}\.png")
            with Image.open(notice.output_path) as copied:
                self.assertEqual(copied.getpixel((6, 6))[-1], 0)
            with Image.open(notice.mask_path) as copied_mask:
                self.assertEqual(copied_mask.getpixel((6, 6)), 0)
            self.assertEqual(
                notice.mask_path.parent, mask.parent, "mask copy pairs with the png copy"
            )
            self.assertEqual(
                output.read_bytes(), before_output, "locked target stays untouched"
            )
            self.assertEqual(mask.read_bytes(), before_mask)
            self.assertFalse(document.is_dirty, "fallback copy is the saved state")
            self.assertEqual(self._leftovers(root), [])

    def test_document_save_non_busy_error_fails_loudly_without_retries(self):
        document = self._dirty_document()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output, mask = self._pair_paths(root, pre_existing=False)
            original_replace = os.replace
            hits: list[Path] = []

            def replace(source, destination):  # type: ignore[no-untyped-def]
                if Path(source).suffix == ".tmp" and Path(destination) == output:
                    hits.append(Path(destination))
                    raise OSError(errno.EIO, "simulated disk failure")
                return original_replace(source, destination)

            sleeps: list[float] = []
            with patch("v3_transparency_preview.os.replace", side_effect=replace), patch(
                "v3_transparency_preview.time.sleep", side_effect=sleeps.append
            ):
                with self.assertRaises(OSError):
                    document.save(output, mask)

            self.assertEqual(len(hits), 1, "a non-busy error must not be retried as busy")
            self.assertEqual(sleeps, [])
            self.assertFalse(list((root / "output").glob("flowers_ready_saved_*.png")))
            self.assertTrue(document.is_dirty, "failed save keeps the unsaved state")
            self.assertEqual(self._leftovers(root), [])

    def test_document_save_without_busy_saves_directly(self):
        document = self._dirty_document()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output, mask = self._pair_paths(root)
            sleeps: list[float] = []
            with patch(
                "v3_transparency_preview.time.sleep", side_effect=sleeps.append
            ):
                document.save(output, mask)

            self.assertEqual(sleeps, [], "no busy: no retries, no pauses")
            self.assertFalse(document.is_dirty)
            self.assertFalse(list((root / "output").glob("flowers_ready_saved_*.png")))
            self.assertEqual(self._leftovers(root), [])

    def test_editor_transient_busy_then_save_success_sets_mask_saved_status(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            page, target = self._new_editor_page(root)
            replace, hits = self._busy_replace(busy_targets={target}, limit=1)
            sleeps: list[float] = []
            with patch("v3_transparency_preview.os.replace", side_effect=replace), patch(
                "v3_transparency_preview.time.sleep", side_effect=sleeps.append
            ), patch("v3_transparency_preview.QMessageBox.critical") as critical, patch(
                "v3_transparency_preview.QMessageBox.warning"
            ) as warning:
                page._save_clicked()

            self.assertEqual(len(hits), 1)
            self.assertEqual(sleeps, [0.3])
            critical.assert_not_called()
            warning.assert_not_called()
            self.assertIn("Маска сохранена", page.contour_status.text())
            self.assertIn(target.name, page.contour_status.text())
            self.assertFalse(page.document.is_dirty)
            self.assertFalse(page._has_unsaved_changes())
            self.assertEqual(self._leftovers(root), [])
            page.deleteLater()

    def test_editor_persistent_busy_saves_timestamped_copy_and_reports_it(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            page, target = self._new_editor_page(root)
            replace, hits = self._busy_replace(busy_targets={target})
            sleeps: list[float] = []
            with patch("v3_transparency_preview.os.replace", side_effect=replace), patch(
                "v3_transparency_preview.time.sleep", side_effect=sleeps.append
            ), patch("v3_transparency_preview.QMessageBox.critical") as critical, patch(
                "v3_transparency_preview.QMessageBox.warning"
            ) as warning:
                page._save_clicked()

            warning.assert_called_once()
            text = warning.call_args.args[2]
            self.assertIn("копию", text)
            self.assertIn("проводник", text)
            self.assertIn("Ничего не потеряно", text)
            critical.assert_not_called()
            self.assertEqual(len(hits), 3)
            self.assertLessEqual(sum(sleeps), 1.0)
            fallback_path = page._busy_fallback_path
            self.assertIsNotNone(fallback_path)
            assert fallback_path is not None
            self.assertTrue(fallback_path.is_file())
            self.assertRegex(fallback_path.name, r"flowers_ready_saved_\d{8}_\d{6}\.png")
            self.assertIn("Сохранено в копию", page.contour_status.text())
            self.assertFalse(page.document.is_dirty)
            self.assertFalse(
                page._has_unsaved_changes(), "saved copy clears the close-dialog loop"
            )
            self.assertEqual(page._saved_copies[target], fallback_path)
            self.assertEqual(self._leftovers(root), [])
            page.deleteLater()

    def test_editor_unwritable_busy_target_reports_busy_cause_and_keeps_dirty(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            page, target = self._new_editor_page(root)
            replace, hits = self._busy_replace()
            with patch("v3_transparency_preview.os.replace", side_effect=replace), patch(
                "v3_transparency_preview.time.sleep"
            ), patch("v3_transparency_preview.QMessageBox.critical") as critical:
                page._save_clicked()

            self.assertGreaterEqual(len(hits), 3, "target and every copy name fought back")
            critical.assert_called_once()
            self.assertEqual(critical.call_args.args[1], "Не удалось заменить занятый PNG")
            self.assertIn("просмотрщик", critical.call_args.args[2])
            self.assertIn("проводник", critical.call_args.args[2])
            self.assertTrue(page.document.is_dirty)
            self.assertTrue(
                page._has_unsaved_changes(), "failed save keeps the close dialog honest"
            )
            self.assertIsNone(page._busy_fallback_path)
            self.assertEqual(self._leftovers(root), [])
            page.deleteLater()

    def test_transparency_dialog_close_save_keeps_window_on_failure_only(self):
        from studio_auto_clipart_flow import _TransparencyDialog

        with tempfile.TemporaryDirectory() as directory:
            page, target = self._new_editor_page(Path(directory))
            dialog = _TransparencyDialog()
            dialog.editor = page
            dialog.ask_unsaved = lambda: QMessageBox.StandardButton.Save
            dialog.show()
            self.assertTrue(page.document.is_dirty)
            with patch.object(
                page._document, "save", side_effect=OSError(errno.EIO, "disk failure")
            ), patch("v3_transparency_preview.QMessageBox.critical") as critical:
                dialog.reject()
            critical.assert_called_once()
            self.assertTrue(
                dialog.isVisible(), "failed save: the close dialog must stay loud"
            )
            self.assertTrue(page.document.is_dirty)
            self.assertTrue(page._has_unsaved_changes())

            with patch("v3_transparency_preview.time.sleep"):
                dialog.reject()

            self.assertFalse(page.document.is_dirty)
            self.assertTrue(target.is_file())
            self.assertFalse(
                dialog.isVisible(), "successful save closes the window immediately"
            )
            page.deleteLater()
            dialog.deleteLater()


if __name__ == "__main__":
    unittest.main()
