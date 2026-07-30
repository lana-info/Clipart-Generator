from __future__ import annotations

import os
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any

from PIL import Image, UnidentifiedImageError
from PyQt6.QtCore import QObject, QSize, Qt, pyqtSignal
from PyQt6.QtGui import QImageReader, QPixmap
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QGroupBox,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QRadioButton,
    QSpinBox,
    QStyle,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from v3_clipart_flow import (
    ClipartFlowError,
    ClipartRunRequest,
    _ScrollableStepPage,
    _legacy_worker_factory,
    _read_legacy_runtime_settings,
    _safe_runtime_error,
    _worker_settings,
)
from v3_components import ButtonVariant, DEFAULT_TOKENS, V3Button, V3DesignTokens
from v3_processing_editor import (
    PROCESSING_RECIPES as _SHARED_PROCESSING_RECIPES,
    ProcessingPipelineEditor,
    RunPlanBuilder,
    apply_processing_recipe as _shared_apply_processing_recipe,
    processing_pipeline_steps as _shared_processing_pipeline_steps,
)
from v3_provider_registry import (
    KIE_MODEL_OPTIONS,
    processing_provider_options,
    provider_requires_api_key,
    provider_requires_network,
    provider_supports_operation,
)
from v3_project_state import (
    GenerationData,
    ImageOperationData,
    ProjectMode,
    ProjectState,
    StepId,
)
from v3_wizard import AppShell


MAX_LOCAL_FILE_BYTES = 100 * 1024 * 1024
MAX_LOCAL_IMAGE_DIMENSION = 32_768
MAX_LOCAL_IMAGE_PIXELS = 70_000_000
MAX_PROCESSING_FILES = 200


class ProcessingFlowError(ValueError):
    pass


@dataclass(frozen=True)
class LocalImageInfo:
    path: str
    name: str
    width: int
    height: int
    color_mode: str
    size_bytes: int

    @property
    def summary(self) -> str:
        size_mb = self.size_bytes / (1024 * 1024)
        return (
            f"{self.name} · {self.width}×{self.height} · "
            f"{self.color_mode} · {size_mb:.1f} МБ"
        )


class WorkspaceSelector(QWidget):
    def __init__(
        self,
        title: str,
        path: str,
        *,
        browse_text: str = "Выбрать",
        changed: Callable[[], None] | None = None,
    ) -> None:
        super().__init__()
        self._changed = changed
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        self.label = QLabel(title)
        self.edit = QLineEdit(path)
        self.edit.setPlaceholderText(title)
        self.browse_button = V3Button(browse_text, ButtonVariant.SECONDARY)
        self.browse_button.clicked.connect(self._browse)
        row.addWidget(self.label)
        row.addWidget(self.edit, 1)
        row.addWidget(self.browse_button)

    def path(self) -> str:
        return self.edit.text().strip()

    def set_path(self, path: str) -> None:
        self.edit.blockSignals(True)
        self.edit.setText(path)
        self.edit.blockSignals(False)

    def _browse(self) -> None:
        selected = QFileDialog.getExistingDirectory(
            self,
            self.label.text(),
            self.path() or os.getcwd(),
        )
        if selected:
            self.set_path(selected)
            if self._changed is not None:
                self._changed()


_OPERATION_FIELDS = tuple(ImageOperationData.__dataclass_fields__)


def _operations(**overrides: Any) -> ImageOperationData:
    values = {
        name: getattr(ImageOperationData(), name)
        for name in _OPERATION_FIELDS
    }
    for name in (
        "visible_mark_cleanup",
        "upscale_before",
        "upscale_after",
        "remove_background",
        "unsharp",
        "edge_shrink",
        "trim",
        "export_300_dpi",
        "remove_exif",
        "remove_xmp",
        "remove_iptc",
        "remove_comments_text",
        "remove_embedded_thumbnail",
        "remove_generator_fields",
        "remove_embedded_c2pa",
    ):
        values[name] = False
    values.update(overrides)
    return ImageOperationData(**values)


PROCESSING_RECIPES: dict[str, tuple[str, str, ImageOperationData | None]] = {
    "basic_enhancement": (
        "Базовое улучшение",
        "Локальная резкость без сетевой передачи.",
        _operations(unsharp=True),
    ),
    "prepare_clipart": (
        "Подготовить клипарт",
        "Локальное удаление фона, очистка края и trim.",
        _operations(
            remove_background=True,
            remove_background_provider="local_rembg",
            edge_shrink=True,
            trim=True,
        ),
    ),
    "check_cleanup": (
        "Проверить и очистить",
        "Удаление служебных метаданных с сохранением ICC и DPI.",
        _operations(
            remove_exif=True,
            remove_xmp=True,
            remove_iptc=True,
            remove_comments_text=True,
            remove_embedded_thumbnail=True,
            remove_generator_fields=True,
        ),
    ),
    "custom": (
        "Свой рецепт",
        "Настройки не меняются; операции выбираются вручную.",
        None,
    ),
}


def apply_processing_recipe(state: ProjectState, recipe: str) -> None:
    if state.mode is not ProjectMode.PROCESSING:
        raise ProcessingFlowError("Рецепт доступен только в режиме обработки")
    if recipe not in PROCESSING_RECIPES:
        raise ProcessingFlowError("Неизвестный рецепт обработки")
    state.processing.recipe = recipe
    preset = PROCESSING_RECIPES[recipe].operations
    if preset is None:
        return
    current = state.processing.operations
    for name in _OPERATION_FIELDS:
        setattr(current, name, getattr(preset, name))


def processing_pipeline_steps(
    operations: ImageOperationData,
) -> tuple[str, ...]:
    steps: list[str] = []
    if operations.visible_mark_cleanup:
        steps.append("Удаление видимой метки")
    if operations.upscale_before:
        steps.append("Апскейл до удаления фона")
    if operations.unsharp:
        steps.append("Unsharp Mask")
    if operations.remove_background:
        steps.append("Удаление фона")
    if operations.upscale_after:
        steps.append("Апскейл после удаления фона")
    if operations.edge_shrink:
        steps.append("Очистка края alpha")
    if operations.trim:
        steps.append("Trim")
    if any(
        (
            operations.remove_exif,
            operations.remove_xmp,
            operations.remove_iptc,
            operations.remove_comments_text,
            operations.remove_embedded_thumbnail,
            operations.remove_generator_fields,
            operations.remove_embedded_c2pa,
        )
    ):
        steps.append("Очистка данных файла")
    if operations.export_300_dpi:
        steps.append("Экспорт 300 DPI")
    if steps:
        steps.append("Экспорт нового PNG")
    return tuple(steps)


PROCESSING_RECIPES = _SHARED_PROCESSING_RECIPES
apply_processing_recipe = _shared_apply_processing_recipe
processing_pipeline_steps = _shared_processing_pipeline_steps


def uses_full_image_changes(operations: ImageOperationData) -> bool:
    return bool(
        operations.visible_mark_cleanup
        or operations.upscale_before
        or operations.upscale_after
        or operations.unsharp
    )

def operation_validation_issues(
    operations: ImageOperationData,
    *,
    allow_full_image_changes: bool,
) -> tuple[str, ...]:
    issues: list[str] = []
    if not processing_pipeline_steps(operations):
        issues.append("processing_operation_required")
    if (
        operations.visible_mark_cleanup
        and operations.visible_mark_cleanup_mode == "confirmed_area"
    ):
        issues.append("confirmed_area_unavailable")
    if uses_full_image_changes(operations) and not allow_full_image_changes:
        issues.append("full_image_change_consent_required")
    return tuple(issues)


def uses_external_processing(operations: ImageOperationData) -> bool:
    selected: list[str] = []
    if operations.upscale_before:
        selected.append(operations.upscale_before_provider)
    if operations.upscale_after:
        selected.append(operations.upscale_after_provider)
    if operations.remove_background:
        selected.append(operations.remove_background_provider)
    try:
        return any(provider_requires_network(provider_id) for provider_id in selected)
    except KeyError:
        return True


def validate_processing_providers(operations: ImageOperationData) -> None:
    try:
        if operations.upscale_before and not provider_supports_operation(
            operations.upscale_before_provider,
            "upscale_before",
        ):
            raise ProcessingFlowError("?????????????????????? ?????????????????? ???????????????? ???? ???????????????? ????????")
        if operations.upscale_after and not provider_supports_operation(
            operations.upscale_after_provider,
            "upscale_after",
        ):
            raise ProcessingFlowError("?????????????????????? ?????????????????? ???????????????? ?????????? ???????????????? ????????")
        if operations.remove_background and not provider_supports_operation(
            operations.remove_background_provider,
            "remove_background",
        ):
            raise ProcessingFlowError("?????????????????????? ?????????????????? ???????????????? ????????")
    except KeyError as error:
        raise ProcessingFlowError(
            f"\u041d\u0435\u0438\u0437\u0432\u0435\u0441\u0442\u043d\u044b\u0439 \u043f\u0440\u043e\u0432\u0430\u0439\u0434\u0435\u0440: {error.args[0]}"
        ) from error


def duplicate_output_names(paths: Sequence[str]) -> tuple[str, ...]:
    seen: set[str] = set()
    duplicates: list[str] = []
    for path in paths:
        key = Path(path).stem.casefold()
        if key in seen and key not in duplicates:
            duplicates.append(key)
        seen.add(key)
    return tuple(duplicates)


def estimate_processing_cost(
    operations: ImageOperationData,
    file_count: int,
) -> str:
    prices = {
        "topaz/upscale": Decimal("0.20"),
        "recraft/crisp-upscale": Decimal("0.0025"),
        "recraft/remove-background": Decimal("0.005"),
    }
    total = Decimal("0")
    complete = True
    if operations.upscale_before and operations.upscale_before_provider == "kie":
        price = prices.get(operations.kie_upscale_model)
        complete = complete and price is not None
        total += (price or Decimal("0")) * file_count
    if operations.upscale_after and operations.upscale_after_provider == "kie":
        price = prices.get(operations.kie_upscale_after_model)
        complete = complete and price is not None
        total += (price or Decimal("0")) * file_count
    if operations.remove_background:
        if operations.remove_background_provider == "kie":
            price = prices.get(operations.kie_remove_bg_model)
            complete = complete and price is not None
            total += (price or Decimal("0")) * file_count
        elif operations.remove_background_provider == "photoroom":
            total += Decimal("0.02") * file_count
    if not uses_external_processing(operations):
        return "локально, без оплаты API"
    if not complete:
        return "стоимость рассчитана не полностью"
    return f"ориентировочно ${total:.3f}"


def processing_change_summary(operations: ImageOperationData) -> tuple[str, str]:
    removed: list[str] = []
    for enabled, label in (
        (operations.remove_exif, "EXIF"),
        (operations.remove_xmp, "XMP"),
        (operations.remove_iptc, "IPTC"),
        (operations.remove_comments_text, "comments/text"),
        (operations.remove_embedded_thumbnail, "embedded thumbnail"),
        (operations.remove_generator_fields, "generator fields"),
        (operations.remove_embedded_c2pa, "embedded C2PA"),
    ):
        if enabled:
            removed.append(label)
    preserved = []
    if operations.preserve_icc:
        preserved.append("ICC")
    if operations.preserve_dpi:
        preserved.append("DPI")
    return (
        ", ".join(removed) if removed else "ничего",
        ", ".join(preserved) if preserved else "нет специальных гарантий",
    )

def missing_processing_runtime_requirements(
    request: ClipartRunRequest,
) -> tuple[str, ...]:
    settings = request.settings
    missing: list[str] = []
    seen: set[str] = set()
    def add_missing(label: str) -> None:
        if label not in seen:
            seen.add(label)
            missing.append(label)
    for enabled_field, provider_field in (
        ("upscale", "upscale_provider"),
        ("upscale_after", "upscale_after_provider"),
        ("remove_bg", "remove_bg_provider"),
    ):
        if not settings.get(enabled_field):
            continue
        provider_id = str(settings.get(provider_field) or "")
        api_key_name = "photoroom_api_key" if provider_id == "photoroom" else "kie_api_key"
        if provider_requires_api_key(provider_id) and not str(settings.get(api_key_name) or "").strip():
            add_missing(
                "KIE API Key" if api_key_name == "kie_api_key" else "PhotoRoom API Key"
            )
    needs_local_upscale = bool(
        (
            settings.get("upscale")
            and settings.get("upscale_provider") == "local_realesrgan"
        )
        or (
            settings.get("upscale_after")
            and settings.get("upscale_after_provider") == "local_realesrgan"
        )
    )
    if needs_local_upscale:
        import main

        _, local_error = main.validate_local_realesrgan_exe(
            settings.get("local_realesrgan_dir")
        )
        if local_error:
            missing.append(local_error)
    return tuple(missing)

def inspect_local_image(path: str | os.PathLike[str]) -> LocalImageInfo:
    source = Path(path).expanduser()
    try:
        if not source.is_file():
            raise ProcessingFlowError("Файл не найден")
        size = source.stat().st_size
    except OSError as error:
        raise ProcessingFlowError("Файл недоступен") from error
    if size <= 0 or size > MAX_LOCAL_FILE_BYTES:
        raise ProcessingFlowError("Файл пустой или превышает 100 МБ")
    try:
        with Image.open(source) as image:
            if getattr(image, "n_frames", 1) != 1:
                raise ProcessingFlowError("Поддерживаются только однокадровые изображения")
            width, height = image.size
            if max(width, height) > MAX_LOCAL_IMAGE_DIMENSION:
                raise ProcessingFlowError("Изображение превышает лимит стороны")
            if width * height > MAX_LOCAL_IMAGE_PIXELS:
                raise ProcessingFlowError("Изображение превышает лимит пикселей")
            color_mode = image.mode
            image.load()
    except ProcessingFlowError:
        raise
    except (OSError, UnidentifiedImageError) as error:
        raise ProcessingFlowError(
            f"Недопустимое изображение: {source.name}"
        ) from error
    return LocalImageInfo(
        path=str(source.resolve()),
        name=source.name,
        width=width,
        height=height,
        color_mode=color_mode,
        size_bytes=size,
    )


class ProcessingFilesPage(_ScrollableStepPage):
    def __init__(
        self,
        state: ProjectState,
        changed: Callable[[], None],
        *,
        tokens: V3DesignTokens = DEFAULT_TOKENS,
    ) -> None:
        super().__init__(
            "Файлы",
            "Добавьте собственные или лицензированные изображения.",
            tokens=tokens,
        )
        self.state = state
        self.changed = changed
        self.setAcceptDrops(True)
        self.file_infos: list[LocalImageInfo] = []

        row = QWidget()
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        self.choose_button = V3Button(
            "Выбрать файлы",
            ButtonVariant.SECONDARY,
        )
        self.choose_button.clicked.connect(self._choose_files)
        row_layout.addWidget(self.choose_button)
        self.clear_button = V3Button("Очистить", ButtonVariant.SECONDARY)
        self.clear_button.clicked.connect(self.clear_files)
        row_layout.addWidget(self.clear_button)
        row_layout.addStretch(1)
        self.add_widget(row)

        self.output_selector = WorkspaceSelector(
            "Папка результата",
            self._default_output_dir(),
            changed=self._sync_output_dir,
        )
        self.output_selector.edit.textChanged.connect(self._sync_output_dir)
        self.add_widget(self.output_selector)

        self.drop_label = QLabel(
            "Перетащите изображения сюда. URL и папки не принимаются."
        )
        self.drop_label.setWordWrap(True)
        self.drop_label.setProperty("v3Status", True)
        self.add_widget(self.drop_label)
        self.files_container = QWidget()
        self.files_layout = QVBoxLayout(self.files_container)
        self.files_layout.setContentsMargins(0, 0, 0, 0)
        self.thumbnail_labels: list[QLabel] = []
        self.add_widget(self.files_container)
        self.error_label = QLabel()
        self.error_label.setWordWrap(True)
        self.error_label.setProperty("state", "error")
        self.add_widget(self.error_label)
        self.refresh_from_state()

    def _changed(self) -> None:
        self.changed()

    def _default_output_dir(self) -> str:
        work_dir = self.state.common.work_dir.strip()
        return str(Path(work_dir) / "output") if work_dir else ""

    def _sync_output_dir(self, *_: Any) -> None:
        value = self.output_selector.path()
        self.state.common.output_dir = value
        self.changed()

    def _choose_files(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            "Выберите изображения",
            "",
            "Images (*.png *.jpg *.jpeg *.webp *.tif *.tiff *.bmp);;All files (*)",
        )
        if paths:
            self.add_files(paths)

    def add_files(self, paths: Sequence[str]) -> tuple[LocalImageInfo, ...]:
        accepted: list[LocalImageInfo] = []
        existing = {
            os.path.normcase(os.path.abspath(path))
            for path in self.state.processing.selected_files
        }
        errors: list[str] = []
        for raw_path in paths:
            if len(existing) >= MAX_PROCESSING_FILES:
                errors.append(f"Максимум {MAX_PROCESSING_FILES} файлов")
                break
            normalized = os.path.normcase(os.path.abspath(str(raw_path)))
            if normalized in existing:
                continue
            try:
                info = inspect_local_image(raw_path)
            except ProcessingFlowError as error:
                errors.append(str(error))
                continue
            accepted.append(info)
            existing.add(normalized)
            self.state.processing.selected_files.append(info.path)
        if accepted:
            self.changed()
        self.error_label.setText(" ".join(errors[:3]))
        self.refresh_from_state()
        return tuple(accepted)

    def clear_files(self) -> None:
        if not self.state.processing.selected_files:
            return
        self.state.processing.selected_files.clear()
        self.state.processing.verification_records.clear()
        self.file_infos.clear()
        self.error_label.clear()
        self.changed()
        self.refresh_from_state()

    def remove_file(self, path: str) -> None:
        target = os.path.normcase(os.path.abspath(path))
        before = len(self.state.processing.selected_files)
        self.state.processing.selected_files = [
            existing
            for existing in self.state.processing.selected_files
            if os.path.normcase(os.path.abspath(existing)) != target
        ]
        self.state.processing.verification_records = [
            record
            for record in self.state.processing.verification_records
            if os.path.normcase(os.path.abspath(record.file_path)) != target
        ]
        if len(self.state.processing.selected_files) != before:
            self.changed()
        self.refresh_from_state()

    def dragEnterEvent(self, event: Any) -> None:
        mime = event.mimeData()
        if mime.hasUrls() and all(url.isLocalFile() for url in mime.urls()):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event: Any) -> None:
        local_files = [
            url.toLocalFile()
            for url in event.mimeData().urls()
            if url.isLocalFile()
        ]
        if local_files:
            self.add_files(local_files)
            event.acceptProposedAction()
        else:
            event.ignore()

    def refresh_from_state(self) -> None:
        default_output = self._default_output_dir()
        if not self.state.common.output_dir and default_output:
            self.state.common.output_dir = default_output
        if not self.output_selector.path():
            self.output_selector.set_path(self.state.common.output_dir or default_output)
        infos: list[LocalImageInfo] = []
        errors: list[str] = []
        for path in self.state.processing.selected_files:
            try:
                infos.append(inspect_local_image(path))
            except ProcessingFlowError:
                errors.append(Path(path).name or "неизвестный файл")
        self.file_infos = infos
        while self.files_layout.count():
            item = self.files_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self.thumbnail_labels = []
        if infos:
            for info in infos:
                card = QGroupBox()
                row = QHBoxLayout(card)
                thumbnail = QLabel()
                thumbnail.setFixedSize(76, 76)
                thumbnail.setAlignment(Qt.AlignmentFlag.AlignCenter)
                reader = QImageReader(info.path)
                target = reader.size().scaled(
                    QSize(72, 72),
                    Qt.AspectRatioMode.KeepAspectRatio,
                )
                if target.isValid():
                    reader.setScaledSize(target)
                image = reader.read()
                if not image.isNull():
                    thumbnail.setPixmap(QPixmap.fromImage(image))
                    thumbnail.setAccessibleName(f"Миниатюра {info.name}")
                else:
                    thumbnail.setText("Нет preview")
                row.addWidget(thumbnail)
                metadata = QLabel(info.summary)
                metadata.setWordWrap(True)
                row.addWidget(metadata, 1)
                remove_button = QToolButton()
                remove_button.setIcon(
                    self.style().standardIcon(QStyle.StandardPixmap.SP_TrashIcon)
                )
                remove_button.setToolTip(f"Удалить {info.name}")
                remove_button.clicked.connect(
                    lambda _checked=False, target=info.path: self.remove_file(target)
                )
                row.addWidget(remove_button)
                self.files_layout.addWidget(card)
                self.thumbnail_labels.append(thumbnail)
        else:
            placeholder = QLabel("Файлы пока не выбраны")
            self.files_layout.addWidget(placeholder)
        if errors:
            self.error_label.setText(
                "Недоступны или недопустимы: " + ", ".join(errors[:3])
            )

    def validation_issues(self) -> tuple[str, ...]:
        issues: list[str] = []
        if not self.state.processing.selected_files:
            issues.append("selected_files_required")
        if len(self.file_infos) != len(self.state.processing.selected_files):
            issues.append("invalid_selected_files")
        if len(self.state.processing.selected_files) > MAX_PROCESSING_FILES:
            issues.append("processing_file_limit_exceeded")
        if duplicate_output_names(self.state.processing.selected_files):
            issues.append("duplicate_output_names")
        return tuple(issues)


class ProcessingRecipePage(_ScrollableStepPage):
    def __init__(
        self,
        state: ProjectState,
        changed: Callable[[], None],
        *,
        tokens: V3DesignTokens = DEFAULT_TOKENS,
    ) -> None:
        super().__init__(
            "Цель обработки",
            "Рецепт только заполняет настройки; их можно изменить на следующем шаге.",
            tokens=tokens,
        )
        self.state = state
        self.changed = changed
        self.buttons: dict[str, QRadioButton] = {}
        group = QGroupBox("Рецепты")
        layout = QVBoxLayout(group)
        for recipe, spec in PROCESSING_RECIPES.items():
            button = QRadioButton(f"{spec.title} — {spec.description}")
            button.toggled.connect(
                lambda checked, value=recipe: self._select(value, checked)
            )
            self.buttons[recipe] = button
            layout.addWidget(button)
        self.add_widget(group)
        self.refresh_from_state()

    def _select(self, recipe: str, checked: bool) -> None:
        if not checked:
            return
        apply_processing_recipe(self.state, recipe)
        self.changed()

    def refresh_from_state(self) -> None:
        selected = self.state.processing.recipe
        if selected not in self.buttons:
            selected = "custom"
            self.state.processing.recipe = selected
        button = self.buttons[selected]
        button.blockSignals(True)
        button.setChecked(True)
        button.blockSignals(False)


class _ProcessingStateAdapter:
    class _ClipartProxy:
        def __init__(self, state: ProjectState) -> None:
            self.operations = state.processing.operations
            self.generation = GenerationData()

    def __init__(self, state: ProjectState) -> None:
        self.common = state.common
        self.runtime = state.runtime
        self.clipart = self._ClipartProxy(state)


class _LegacyProcessingPipelinePage(_ScrollableStepPage):
    _BOOL_LABELS = {
        "visible_mark_cleanup": "Удалить видимую метку — локальная реконструкция пикселей",
        "upscale_before": "Апскейл до удаления фона — увеличит изображение",
        "unsharp": "Unsharp Mask — усилит резкость",
        "remove_background": "Удалить фон — создаст прозрачность",
        "upscale_after": "Апскейл после удаления фона — увеличит PNG",
        "edge_shrink": "Очистить край alpha — уменьшит цветную кайму",
        "trim": "Trim — обрежет пустые поля",
        "export_300_dpi": "Экспорт 300 DPI — запишет разрешение печати",
        "remove_exif": "Удалить EXIF",
        "remove_xmp": "Удалить XMP",
        "remove_iptc": "Удалить IPTC",
        "remove_comments_text": "Удалить comments/text",
        "remove_embedded_thumbnail": "Удалить embedded thumbnail",
        "remove_generator_fields": "Удалить generator fields",
        "remove_embedded_c2pa": "Удалить embedded C2PA",
    }

    def __init__(
        self,
        state: ProjectState,
        changed: Callable[[], None],
        *,
        tokens: V3DesignTokens = DEFAULT_TOKENS,
    ) -> None:
        super().__init__(
            "Обработка изображений",
            "Операции выполняются сверху вниз; рецепт можно полностью изменить.",
            tokens=tokens,
        )
        self.project_state = state
        self.changed = changed
        self.operation_widgets: dict[str, QCheckBox] = {}
        operations_group = QGroupBox("Обработка изображений")
        operations_layout = QVBoxLayout(operations_group)
        for name, label in self._BOOL_LABELS.items():
            checkbox = QCheckBox(label)
            checkbox.toggled.connect(
                lambda checked, field=name: self._set_bool(field, checked)
            )
            self.operation_widgets[name] = checkbox
            operations_layout.addWidget(checkbox)
        self.add_widget(operations_group)

        provider_group = QGroupBox("Провайдеры")
        provider_layout = QVBoxLayout(provider_group)
        self.upscale_before_provider = self._provider_combo(
            provider_layout,
            "Апскейл до",
            "upscale_before_provider",
            processing_provider_options("upscale_before_provider"),
        )
        self.remove_background_provider = self._provider_combo(
            provider_layout,
            "Удаление фона",
            "remove_background_provider",
            processing_provider_options("remove_background_provider"),
        )
        self.upscale_after_provider = self._provider_combo(
            provider_layout,
            "Апскейл после",
            "upscale_after_provider",
            processing_provider_options("upscale_after_provider"),
        )
        self.kie_upscale_model = self._provider_combo(
            provider_layout,
            "KIE модель апскейла до",
            "kie_upscale_model",
            KIE_MODEL_OPTIONS,
        )
        self.kie_upscale_after_model = self._provider_combo(
            provider_layout,
            "KIE модель апскейла после",
            "kie_upscale_after_model",
            KIE_MODEL_OPTIONS,
        )
        self.add_widget(provider_group)

        settings_group = QGroupBox("Параметры этапов")
        settings_form = QFormLayout(settings_group)
        self.unsharp_amount = self._int_setting(settings_form, "Unsharp amount", "unsharp_amount", 0, 500)
        self.unsharp_radius = self._double_setting(settings_form, "Unsharp radius", "unsharp_radius", 0.1, 200.0)
        self.unsharp_threshold = self._int_setting(settings_form, "Unsharp threshold", "unsharp_threshold", 0, 255)
        self.edge_shrink_pixels = self._int_setting(settings_form, "Очистка края, px", "edge_shrink_pixels", 1, 3)
        self.upscale_factor = self._int_setting(settings_form, "Множитель апскейла", "upscale_factor", 1, 16)
        self.trim_mode = QComboBox()
        for label, value in (("Alpha", "alpha"), ("Белому", "white"), ("Чёрному", "black")):
            self.trim_mode.addItem(label, value)
        self.trim_mode.currentIndexChanged.connect(
            lambda _index: self._set_value("trim_mode", self.trim_mode.currentData())
        )
        settings_form.addRow("Trim по", self.trim_mode)
        self.add_widget(settings_group)

        self.allow_full_image_changes = QCheckBox(
            "Разрешить глубокую обработку скрытых водяных знаков (SynthID)"
        )
        self.allow_full_image_changes.toggled.connect(changed)
        self.add_widget(self.allow_full_image_changes)
        self.order_label = QLabel()
        self.order_label.setWordWrap(True)
        self.order_label.setProperty("v3Status", True)
        self.add_widget(self.order_label)
        self.refresh_from_state()

    def _provider_combo(
        self,
        layout: QVBoxLayout,
        label: str,
        field: str,
        options: Sequence[tuple[str, str]],
    ) -> QComboBox:
        row = QWidget()
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.addWidget(QLabel(label))
        combo = QComboBox()
        for option_label, value in options:
            combo.addItem(option_label, value)
        combo.currentIndexChanged.connect(
            lambda _index, name=field, widget=combo: self._set_value(
                name, widget.currentData()
            )
        )
        row_layout.addWidget(combo, 1)
        layout.addWidget(row)
        return combo

    def _int_setting(
        self,
        form: QFormLayout,
        label: str,
        field: str,
        minimum: int,
        maximum: int,
    ) -> QSpinBox:
        spin = QSpinBox()
        spin.setRange(minimum, maximum)
        spin.valueChanged.connect(lambda value, name=field: self._set_value(name, value))
        form.addRow(label, spin)
        return spin

    def _double_setting(
        self,
        form: QFormLayout,
        label: str,
        field: str,
        minimum: float,
        maximum: float,
    ) -> QDoubleSpinBox:
        spin = QDoubleSpinBox()
        spin.setRange(minimum, maximum)
        spin.setDecimals(1)
        spin.valueChanged.connect(lambda value, name=field: self._set_value(name, value))
        form.addRow(label, spin)
        return spin
    def _set_bool(self, field: str, checked: bool) -> None:
        self._set_value(field, bool(checked))

    def _set_value(self, field: str, value: Any) -> None:
        setattr(self.project_state.processing.operations, field, value)
        self.project_state.processing.recipe = "custom"
        self.changed()
        self._refresh_order()

    @staticmethod
    def _select_combo(combo: QComboBox, value: str) -> None:
        index = combo.findData(value)
        if index >= 0:
            combo.setCurrentIndex(index)

    def _refresh_order(self) -> None:
        steps = processing_pipeline_steps(self.project_state.processing.operations)
        self.order_label.setText(
            "Порядок: " + (" → ".join(steps) if steps else "операции не выбраны")
        )

    def refresh_from_state(self) -> None:
        operations = self.project_state.processing.operations
        for name, checkbox in self.operation_widgets.items():
            checkbox.blockSignals(True)
            checkbox.setChecked(bool(getattr(operations, name)))
            checkbox.blockSignals(False)
        for combo, value in (
            (self.upscale_before_provider, operations.upscale_before_provider),
            (self.remove_background_provider, operations.remove_background_provider),
            (self.upscale_after_provider, operations.upscale_after_provider),
            (self.kie_upscale_model, operations.kie_upscale_model),
            (self.kie_upscale_after_model, operations.kie_upscale_after_model),
            (self.trim_mode, operations.trim_mode),
        ):
            combo.blockSignals(True)
            self._select_combo(combo, value)
            combo.blockSignals(False)
        for spin, value in (
            (self.unsharp_amount, operations.unsharp_amount),
            (self.unsharp_radius, operations.unsharp_radius),
            (self.unsharp_threshold, operations.unsharp_threshold),
            (self.edge_shrink_pixels, operations.edge_shrink_pixels),
            (self.upscale_factor, operations.upscale_factor),
        ):
            spin.blockSignals(True)
            spin.setValue(value)
            spin.blockSignals(False)
        self._refresh_order()

    def validation_issues(self) -> tuple[str, ...]:
        return operation_validation_issues(
            self.project_state.processing.operations,
            allow_full_image_changes=self.allow_full_image_changes.isChecked(),
        )


class _SharedProcessingPipelinePage(ProcessingPipelineEditor):
    def __init__(
        self,
        state: ProjectState,
        changed: Callable[[], None],
        *,
        tokens: V3DesignTokens = DEFAULT_TOKENS,
    ) -> None:
        super().__init__(
            state.processing,
            changed,
            title="Обработка изображений",
            description="Операции выполняются сверху вниз; рецепт можно полностью изменить.",
            include_cleanup=False,
            tokens=tokens,
        )
        self.project_state = state
        self.allow_full_image_changes = QCheckBox(
            "Разрешить глубокую обработку скрытых водяных знаков (SynthID)"
        )
        self.allow_full_image_changes.toggled.connect(changed)
        self.add_widget(self.allow_full_image_changes)

    def validation_issues(self) -> tuple[str, ...]:
        return operation_validation_issues(
            self.project_state.processing.operations,
            allow_full_image_changes=self.allow_full_image_changes.isChecked(),
        )


ProcessingPipelinePage = _SharedProcessingPipelinePage


class ProcessingReviewRunPage(_ScrollableStepPage):
    def __init__(
        self,
        state: ProjectState,
        files_page: ProcessingFilesPage,
        pipeline_page: ProcessingPipelinePage,
        *,
        tokens: V3DesignTokens = DEFAULT_TOKENS,
    ) -> None:
        super().__init__(
            "Сравнение и запуск",
            "Проверьте порядок, место сохранения и сетевую передачу.",
            tokens=tokens,
        )
        self.state = state
        self.files_page = files_page
        self.pipeline_page = pipeline_page
        self.summary_label = QLabel()
        self.summary_label.setWordWrap(True)
        self.pipeline_label = QLabel()
        self.pipeline_label.setWordWrap(True)
        self.output_label = QLabel()
        self.output_label.setWordWrap(True)
        self.warning_label = QLabel()
        self.warning_label.setWordWrap(True)
        self.warning_label.setProperty("state", "warning")
        self.network_consent = QCheckBox(
            "Разрешаю передачу файлов выбранным внешним сервисам"
        )
        self.requirements_label = QLabel()
        self.requirements_label.setWordWrap(True)
        self.run_status_label = QLabel()
        self.run_status_label.setWordWrap(True)
        for widget in (
            self.summary_label,
            self.pipeline_label,
            self.output_label,
            self.warning_label,
            self.network_consent,
            self.requirements_label,
            self.run_status_label,
        ):
            self.add_widget(widget)
        self.refresh_from_state()

    def refresh_from_state(self) -> None:
        operations = self.state.processing.operations
        files = self.state.processing.selected_files
        work_dir = self.state.common.work_dir
        output_dir = self.state.common.output_dir.strip()
        if not output_dir and work_dir:
            output_dir = str(Path(work_dir) / "output")
            self.state.common.output_dir = output_dir
        if not output_dir:
            output_dir = "не выбрана"
        steps = processing_pipeline_steps(operations)
        removed, preserved = processing_change_summary(operations)
        cost = estimate_processing_cost(operations, len(files))
        recipe = PROCESSING_RECIPES.get(
            self.state.processing.recipe,
            PROCESSING_RECIPES["custom"],
        )
        self.network_consent.setChecked(True)
        self.network_consent.setVisible(False)
        self.summary_label.setText(
            f"Файлов: {len(files)} · рецепт: "
            f"{recipe.title} "
            f"· стоимость: {cost} · очищается: {removed} · сохраняется: {preserved}"
        )
        self.pipeline_label.setText(
            "Порядок: " + (" → ".join(steps) if steps else "операции не выбраны")
        )
        self.output_label.setText(
            f"Папка результата: {output_dir}. Исходники не перезаписываются."
        )
        external = uses_external_processing(operations)
        self.network_consent.setVisible(external)
        warnings: list[str] = []
        if operations.remove_background or operations.edge_shrink or operations.trim:
            warnings.append("Прозрачность и границы объекта могут измениться.")
        if uses_full_image_changes(operations):
            warnings.append("Выбран этап, способный изменить пиксели всего изображения.")
        if external:
            warnings.append(
                f"Файл будет передан внешнему сервису; {cost}."
            )
        else:
            warnings.append("Сетевая передача не требуется.")
        self.warning_label.setText(" ".join(warnings))

    def validation_issues(self) -> tuple[str, ...]:
        issues = list(self.files_page.validation_issues())
        issues.extend(self.pipeline_page.validation_issues())
        return tuple(issues)

    def set_preflight_status(self, text: str, *, ready: bool) -> None:
        prefix = "✓ " if ready else "✕ "
        self.requirements_label.setText(prefix + text[:500])
        self.requirements_label.setProperty(
            "state", "default" if ready else "error"
        )

    def set_run_status(self, text: str, *, error: bool = False) -> None:
        self.run_status_label.setText(("✕ " if error else "✓ ") + text[:500])


def build_processing_run_request(
    state: ProjectState,
    runtime_settings: Mapping[str, Any] | None = None,
    *,
    allow_full_image_changes: bool,
    external_transfer_consent: bool,
) -> ClipartRunRequest:
    if state.mode is not ProjectMode.PROCESSING:
        raise ProcessingFlowError("Запуск доступен только в режиме обработки")
    work_dir = Path(state.common.work_dir).expanduser()
    if not work_dir.is_dir() or not os.access(work_dir, os.W_OK):
        raise ProcessingFlowError(
            "Рабочая папка не существует или недоступна для записи"
        )
    if not state.processing.selected_files:
        raise ProcessingFlowError("Добавьте хотя бы один файл")
    if len(state.processing.selected_files) > MAX_PROCESSING_FILES:
        raise ProcessingFlowError(f"Максимум {MAX_PROCESSING_FILES} файлов за запуск")
    duplicates = duplicate_output_names(state.processing.selected_files)
    if duplicates and not bool((runtime_settings or {}).get("overwrite_existing", False)):
        raise ProcessingFlowError(
            "Одинаковые имена создадут один путь результата: "
            + ", ".join(duplicates[:3])
        )
    for path in state.processing.selected_files:
        inspect_local_image(path)
    validate_processing_providers(state.processing.operations)
    issues = operation_validation_issues(
        state.processing.operations,
        allow_full_image_changes=allow_full_image_changes,
    )
    if issues:
        raise ProcessingFlowError("Исправьте настройки pipeline: " + ", ".join(issues))
    adapter = _ProcessingStateAdapter(state)
    settings = _worker_settings(adapter, runtime_settings)
    settings["run_mode"] = "process_only"
    settings["output_dir"] = state.common.output_dir or str(work_dir / "output")
    return ClipartRunRequest(
        mode="mode2_process",
        work_dir=str(work_dir),
        settings=settings,
        selected_files=list(state.processing.selected_files),
    )


class ProcessingFlowController(QObject):
    started = pyqtSignal(object)
    progress = pyqtSignal(str)
    progress_value = pyqtSignal(int)
    finished = pyqtSignal(str)
    error = pyqtSignal(str)

    def __init__(
        self,
        shell: AppShell,
        *,
        runtime_settings_provider: Callable[[], Mapping[str, Any]] | None = None,
        worker_factory: Callable[..., Any] | None = None,
    ) -> None:
        super().__init__(shell)
        self.shell = shell
        self.runtime_settings_provider = (
            runtime_settings_provider or _read_legacy_runtime_settings
        )
        self.worker_factory = worker_factory or _legacy_worker_factory
        self.worker: Any | None = None
        self._runtime_settings: Mapping[str, Any] = {}
        from v3_run_queue import RunQueueSupport

        self.run_queue = RunQueueSupport(self, ProjectMode.PROCESSING)
        self.pages: dict[StepId, QWidget] = {}
        self._install_pages()
        shell.step_changed.connect(self._step_changed)
        shell.run_requested.connect(self._run_requested)

    def _install_pages(self) -> None:
        from v3_evidence_center import EvidenceCenterPage

        changed = self.shell.mark_dirty
        files_page = ProcessingFilesPage(self.shell.state, changed, tokens=self.shell.tokens)
        recipe_page = ProcessingRecipePage(self.shell.state, changed, tokens=self.shell.tokens)
        pipeline_page = ProcessingPipelinePage(
            self.shell.state, changed, tokens=self.shell.tokens
        )
        evidence_page = EvidenceCenterPage(
            self.shell.state,
            changed,
            tokens=self.shell.tokens,
        )
        review_page = ProcessingReviewRunPage(
            self.shell.state, files_page, pipeline_page, tokens=self.shell.tokens
        )
        self.pages = {
            StepId.FILES: files_page,
            StepId.GOAL: recipe_page,
            StepId.PIPELINE: pipeline_page,
            StepId.EVIDENCE: evidence_page,
            StepId.REVIEW_RUN: review_page,
            StepId.RESULTS: self.run_queue.page,
        }
        for step, page in self.pages.items():
            self.shell.set_step_page(ProjectMode.PROCESSING, step, page)
        self.shell.refresh()

    @property
    def review_page(self) -> ProcessingReviewRunPage:
        page = self.pages[StepId.REVIEW_RUN]
        assert isinstance(page, ProcessingReviewRunPage)
        return page

    @property
    def files_page(self) -> ProcessingFilesPage:
        page = self.pages[StepId.FILES]
        assert isinstance(page, ProcessingFilesPage)
        return page

    @property
    def pipeline_page(self) -> ProcessingPipelinePage:
        page = self.pages[StepId.PIPELINE]
        assert isinstance(page, ProcessingPipelinePage)
        return page

    def _step_changed(self, mode: str, step: str) -> None:
        if mode != ProjectMode.PROCESSING.value:
            return
        page = self.pages.get(StepId(step))
        refresher = getattr(page, "refresh_from_state", None)
        if callable(refresher):
            refresher()
        if StepId(step) is StepId.REVIEW_RUN:
            self._refresh_preflight()

    def _request(self) -> ClipartRunRequest:
        file_issues = self.files_page.validation_issues()
        if file_issues:
            raise ProcessingFlowError(
                "Подтвердите права и повторно проверьте выбранные файлы"
            )
        runtime = self.runtime_settings_provider()
        if not isinstance(runtime, Mapping):
            raise ProcessingFlowError("Настройки запуска повреждены")
        self._runtime_settings = runtime
        return build_processing_run_request(
            self.shell.state,
            runtime,
            allow_full_image_changes=(
                self.pipeline_page.allow_full_image_changes.isChecked()
            ),
            external_transfer_consent=True,
        )

    def _refresh_preflight(self) -> None:
        try:
            request = self._request()
            missing = missing_processing_runtime_requirements(request)
            if missing:
                raise ProcessingFlowError(
                    "Укажите в настройках: " + ", ".join(missing)
                )
        except Exception as error:
            self.review_page.set_preflight_status(str(error), ready=False)
            return
        self.review_page.set_preflight_status("Запуск готов.", ready=True)

    def _run_requested(self, mode: str) -> None:
        if mode == ProjectMode.PROCESSING.value:
            self.start()

    def start(self) -> ClipartRunRequest | None:
        if self.worker is not None and bool(self.worker.isRunning()):
            self.review_page.set_run_status("Запуск уже выполняется", error=True)
            return None
        try:
            request = self._request()
            missing = missing_processing_runtime_requirements(request)
            if missing:
                raise ProcessingFlowError(
                    "Укажите в настройках: " + ", ".join(missing)
                )
            worker = self.worker_factory(**request.worker_kwargs())
        except Exception as error:
            message = _safe_runtime_error(error, self._runtime_settings)
            self.review_page.set_run_status(message, error=True)
            self.error.emit(message)
            return None
        self.worker = worker
        self.run_queue.start_new(request)
        self.run_queue.connect_worker(worker)
        worker.start()
        self.shell.show_results()
        self.review_page.set_run_status("Запуск передан pipeline 2.0")
        self.started.emit(request)
        return request

    def _finished(self, message: str) -> None:
        self.run_queue.finished()
        safe = _safe_runtime_error(message, self._runtime_settings)
        self.review_page.set_run_status(safe)
        self.finished.emit(safe)

    def _error(self, message: str) -> None:
        self.run_queue.fatal_error(message)
        safe = _safe_runtime_error(message, self._runtime_settings)
        self.review_page.set_run_status(safe, error=True)
        self.error.emit(safe)

    def stop(self) -> None:
        if self.worker is not None and hasattr(self.worker, "stop"):
            self.worker.stop()


def install_processing_flow(
    shell: AppShell,
    *,
    runtime_settings_provider: Callable[[], Mapping[str, Any]] | None = None,
    worker_factory: Callable[..., Any] | None = None,
) -> ProcessingFlowController:
    if not isinstance(shell, AppShell):
        raise TypeError("shell must be an AppShell")
    existing = getattr(shell, "processing_flow_controller", None)
    if isinstance(existing, ProcessingFlowController):
        return existing
    controller = ProcessingFlowController(
        shell,
        runtime_settings_provider=runtime_settings_provider,
        worker_factory=worker_factory,
    )
    shell.processing_flow_controller = controller
    return controller
