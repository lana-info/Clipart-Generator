"""Capture safe, deterministic Vibix Images screenshots for the user guide.

The script renders real PyQt widgets with synthetic demo data. It never reads
stored credentials, contacts providers, starts a worker, or writes a project
draft.
"""

from __future__ import annotations

import argparse
import csv
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from PIL import Image, ImageDraw
from PyQt6.QtCore import QEvent
from PyQt6.QtWidgets import QApplication, QLabel, QVBoxLayout, QWidget

from v3_api_settings import ApiSettingsDialog
from v3_clipart_flow import install_clipart_flow
from v3_components import apply_v3_theme
from v3_mode_selection import ModeSelectionScreen
from v3_pinterest_flow import install_pinterest_flow
from v3_processing_flow import install_processing_flow
from v3_project_state import (
    ImageOperationData,
    ProjectMode,
    ProjectState,
    PromptEntry,
    PromptGeneratorData,
    StepId,
)
from v3_prompt_csv_import import PromptCsvImportDialog
from v3_transparency_preview import ClipartTransparencyPreview
from v3_wizard import AppShell


OUTPUT = ROOT / "docs" / "user-guide" / "assets"
SCREEN_SIZE = (1366, 900)


def process_events() -> None:
    QApplication.processEvents()
    QApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    QApplication.processEvents()


def capture(widget: QWidget, filename: str, *, size: tuple[int, int] = SCREEN_SIZE) -> None:
    widget.resize(*size)
    widget.show()
    process_events()
    destination = OUTPUT / filename
    if not widget.grab().save(str(destination), "PNG"):
        raise RuntimeError(f"Could not save screenshot: {destination}")
    widget.close()
    process_events()


def demo_operations() -> ImageOperationData:
    return ImageOperationData(
        upscale_before=True,
        upscale_before_provider="local_realesrgan",
        local_realesrgan_scale=2,
        remove_background=True,
        remove_background_provider="local_chroma_key",
        chroma_key_color="blue",
        chroma_key_tolerance=32,
        chroma_key_softness=8,
        edge_shrink=True,
        edge_shrink_pixels=1,
        trim=True,
        trim_mode="alpha",
        export_300_dpi=True,
        remove_exif=True,
        remove_xmp=True,
        remove_generator_fields=True,
    )


def capture_mode_selection() -> None:
    screen = ModeSelectionScreen()
    screen.set_license_status("Лицензия активна", "Онлайн-проверка выполнена")
    capture(screen, "01-mode-selection.png")


def capture_api_settings() -> None:
    with patch("v3_api_settings.load_credentials", return_value={}):
        dialog = ApiSettingsDialog(initial={})
    apply_v3_theme(dialog)
    capture(dialog, "02-api-settings.png", size=(1000, 720))


def clipart_state(work_dir: Path) -> ProjectState:
    state = ProjectState(mode=ProjectMode.CLIPART)
    state.common.project_name = "Лесные звери"
    state.common.work_dir = str(work_dir)
    state.set_output_dir_for_mode(str(work_dir / "output"), ProjectMode.CLIPART)
    state.clipart.prompt_generator = PromptGeneratorData(
        theme="Акварельные лесные звери для детского клипарта",
        subjects=["лиса", "медвежонок", "заяц"],
        variations=["сидит", "держит букет полевых цветов"],
        style="мягкая акварель, ручная иллюстрация",
        palette="терракотовый, кремовый, шалфейный",
        composition="один объект целиком, по центру",
        background="ровный однотонный фон без теней",
        consistency="одинаковая толщина линий и масштаб",
        restrictions=["текст", "рамки", "водяные знаки", "обрезанные уши"],
        chroma_key_enabled=True,
        chroma_key_color="blue",
    )
    state.clipart.prompts = [
        PromptEntry("Акварельная лиса сидит, один объект целиком, по центру"),
        PromptEntry("Акварельный медвежонок держит букет полевых цветов"),
        PromptEntry("Акварельный заяц сидит, мягкая природная палитра"),
    ]
    state.clipart.operations = demo_operations()
    return state


def capture_clipart_pages(work_dir: Path) -> None:
    state = clipart_state(work_dir)
    shell = AppShell(state)
    controller = install_clipart_flow(
        shell,
        runtime_settings_provider=lambda: {},
        authorization_provider=lambda: None,
    )
    shell.resize(*SCREEN_SIZE)

    state.set_step(StepId.PROMPTS)
    page = controller.pages[StepId.PROMPTS]
    page.source_buttons[0].click()
    shell.refresh()
    capture(shell, "03-clipart-prompt-generator.png")

    shell = AppShell(state)
    controller = install_clipart_flow(shell, runtime_settings_provider=lambda: {})
    state.set_step(StepId.PROMPT_REVIEW)
    controller.pages[StepId.PROMPT_REVIEW].refresh_from_state()
    shell.refresh()
    capture(shell, "05-clipart-prompt-review.png")

    shell = AppShell(state)
    controller = install_clipart_flow(shell, runtime_settings_provider=lambda: {})
    state.set_step(StepId.GENERATION)
    controller.pages[StepId.GENERATION].refresh_from_state()
    shell.refresh()
    capture(shell, "06-clipart-generation.png")

    shell = AppShell(state)
    controller = install_clipart_flow(shell, runtime_settings_provider=lambda: {})
    state.set_step(StepId.PROCESSING_OPTIONS)
    controller.pages[StepId.PROCESSING_OPTIONS].refresh_from_state()
    shell.refresh()
    capture(shell, "07-clipart-processing.png")

    shell = AppShell(state)
    controller = install_clipart_flow(shell, runtime_settings_provider=lambda: {})
    state.set_output_dir_for_mode(
        "C:/Users/Имя/Pictures/Vibix Images/Лесные звери/output",
        ProjectMode.CLIPART,
    )
    state.set_step(StepId.REVIEW_RUN)
    controller.pages[StepId.REVIEW_RUN].refresh_from_state()
    shell.refresh()
    capture(shell, "08-clipart-review.png")


def capture_csv_dialog(work_dir: Path) -> None:
    csv_path = work_dir / "clipart-prompts.csv"
    with csv_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["prompt", "references"])
        writer.writerow(["Watercolor fox, isolated clipart", ""])
        writer.writerow(["Watercolor bear with flowers", "bear-front.png | bear-pose.png"])
        writer.writerow(["Watercolor rabbit, soft natural palette", "rabbit.png"])
    dialog = PromptCsvImportDialog(csv_path)
    references_index = dialog.references_column_combo.findText("references")
    if references_index >= 0:
        dialog.references_column_combo.setCurrentIndex(references_index)
        dialog._refresh_preview()
    apply_v3_theme(dialog)
    capture(dialog, "04-csv-import.png", size=(940, 680))


def capture_pinterest_pages(work_dir: Path) -> None:
    state = ProjectState(mode=ProjectMode.PINTEREST)
    state.common.work_dir = str(work_dir)
    state.set_output_dir_for_mode(str(work_dir / "pinterest-output"), ProjectMode.PINTEREST)
    state.pinterest.prompts = [
        PromptEntry("Vertical Pinterest pin, cozy reading nook, warm editorial photo"),
        PromptEntry("Vertical Pinterest pin, neutral home office, natural daylight"),
    ]
    shell = AppShell(state)
    controller = install_pinterest_flow(shell, runtime_settings_provider=lambda: {})
    state.set_step(StepId.PROMPTS)
    controller.pages[StepId.PROMPTS].refresh_from_state()
    shell.refresh()
    capture(shell, "09-pinterest-prompts.png")

    shell = AppShell(state)
    controller = install_pinterest_flow(shell, runtime_settings_provider=lambda: {})
    state.set_step(StepId.PIN_FORMAT_MODEL)
    controller.pages[StepId.PIN_FORMAT_MODEL].refresh_from_state()
    shell.refresh()
    capture(shell, "10-pinterest-format.png")


def create_demo_image(path: Path, *, transparent: bool = False) -> Image.Image:
    mode = "RGBA" if transparent else "RGB"
    background = (0, 0, 0, 0) if transparent else (237, 241, 236)
    image = Image.new(mode, (720, 720), background)
    draw = ImageDraw.Draw(image)
    draw.ellipse((170, 120, 550, 570), fill=(190, 105, 55, 255) if transparent else (190, 105, 55))
    draw.ellipse((205, 70, 335, 230), fill=(190, 105, 55, 255) if transparent else (190, 105, 55))
    draw.ellipse((385, 70, 515, 230), fill=(190, 105, 55, 255) if transparent else (190, 105, 55))
    draw.ellipse((280, 255, 325, 300), fill=(28, 36, 44, 255) if transparent else (28, 36, 44))
    draw.ellipse((395, 255, 440, 300), fill=(28, 36, 44, 255) if transparent else (28, 36, 44))
    image.save(path, format="PNG")
    return image


def capture_processing_pages(work_dir: Path) -> None:
    first = work_dir / "fox-clipart.png"
    second = work_dir / "bear-clipart.png"
    create_demo_image(first)
    create_demo_image(second)
    state = ProjectState(mode=ProjectMode.PROCESSING)
    state.common.work_dir = str(work_dir)
    state.set_output_dir_for_mode(
        "C:/Users/Имя/Pictures/Vibix Images/Обработанные",
        ProjectMode.PROCESSING,
    )
    state.processing.selected_files = [str(first), str(second)]
    state.processing.recipe = "custom"
    state.processing.operations = demo_operations()

    shell = AppShell(state)
    controller = install_processing_flow(shell, runtime_settings_provider=lambda: {})
    state.set_step(StepId.FILES)
    controller.pages[StepId.FILES].refresh_from_state()
    shell.refresh()
    capture(shell, "11-processing-files.png")

    shell = AppShell(state)
    controller = install_processing_flow(shell, runtime_settings_provider=lambda: {})
    state.set_step(StepId.PIPELINE)
    controller.pages[StepId.PIPELINE].refresh_from_state()
    shell.refresh()
    capture(shell, "12-processing-pipeline.png")


def capture_transparency_editor(work_dir: Path) -> None:
    image_path = work_dir / "transparent-fox.png"
    image = create_demo_image(image_path, transparent=True)
    preview = ClipartTransparencyPreview()
    preview.set_image(image)
    preview.background_combo.setCurrentText("Ярко-розовый")
    preview.zoom_spin.setValue(75)
    container = QWidget()
    apply_v3_theme(container)
    layout = QVBoxLayout(container)
    title = QLabel("Редактор прозрачности клипарта")
    title.setProperty("v3Title", True)
    subtitle = QLabel("Проверьте края на контрастном фоне и исправьте alpha-маску кистью.")
    subtitle.setWordWrap(True)
    layout.addWidget(title)
    layout.addWidget(subtitle)
    layout.addWidget(preview, 1)
    capture(container, "13-transparency-editor.png", size=(980, 820))


def main(argv: list[str] | None = None) -> int:
    global OUTPUT
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=OUTPUT,
        help="Directory for generated PNG screenshots",
    )
    args = parser.parse_args(argv)
    OUTPUT = args.output_dir.expanduser().resolve()
    OUTPUT.mkdir(parents=True, exist_ok=True)
    app = QApplication.instance() or QApplication([])
    with tempfile.TemporaryDirectory(prefix="vibix-user-guide-") as temp:
        work_dir = Path(temp)
        capture_mode_selection()
        capture_api_settings()
        capture_clipart_pages(work_dir)
        capture_csv_dialog(work_dir)
        capture_pinterest_pages(work_dir)
        capture_processing_pages(work_dir)
        capture_transparency_editor(work_dir)
    app.processEvents()
    for path in sorted(OUTPUT.glob("*.png")):
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
