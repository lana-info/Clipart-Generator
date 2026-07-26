from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

from PyQt6.QtCore import QUrl
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from metadata_cleanup import MetadataCleanupOptions
from metadata_inspector import inspect_image_metadata
from v3_components import ButtonVariant, DEFAULT_TOKENS, V3Button, V3DesignTokens
from v3_project_state import (
    ImageOperationData,
    ProjectMode,
    ProjectState,
    VerificationRecordData,
)
from watermark_status import (
    FileHintStatus,
    PixelEvidenceSource,
    PixelEvidenceStage,
    PixelEvidenceStatus,
    PixelMarkerType,
    create_pixel_watermark_status,
)


GEMINI_VERIFY_URL = "https://gemini.google.com/"
GEMINI_HELP_URL = (
    "https://support.google.com/gemini/answer/16722517?hl=en"
)
OPENAI_VERIFY_URL = "https://openai.com/research/verify/"
MAX_EVIDENCE_REPORT_BYTES = 2 * 1024 * 1024

_RECORDED_STATUSES = (
    ("Не проверялось", "not_verified"),
    ("Обнаружено выбранной проверкой", "detected"),
    ("Не обнаружено выбранной проверкой", "not_detected"),
    ("Проверка не поддерживается / результат неясен", "unsupported"),
)
_RECORDED_STAGES = (("Исходный файл", "input"), ("Результат", "output"))
_CHECKED_STATUSES = frozenset({"detected", "not_detected"})


class EvidenceCenterError(ValueError):
    pass


class EvidenceCard(QGroupBox):
    def __init__(
        self,
        title: str,
        description: str,
        *,
        tokens: V3DesignTokens = DEFAULT_TOKENS,
    ) -> None:
        super().__init__(title)
        self.tokens = tokens
        layout = QVBoxLayout(self)
        layout.setSpacing(tokens.space_2)
        self.description_label = QLabel(description)
        self.description_label.setWordWrap(True)
        self.description_label.setProperty("v3Description", True)
        layout.addWidget(self.description_label)
        self.status_label = QLabel()
        self.status_label.setWordWrap(True)
        self.status_label.setProperty("v3Status", True)
        layout.addWidget(self.status_label)
        self.content_layout = layout

    def add_widget(self, widget: QWidget) -> None:
        self.content_layout.addWidget(widget)

    def set_status(self, text: str, *, warning: bool = False) -> None:
        self.status_label.setText(text)
        self.status_label.setAccessibleName(text)
        self.status_label.setProperty("state", "warning" if warning else "default")


def cleanup_options_from_operations(
    operations: ImageOperationData,
) -> MetadataCleanupOptions:
    if not isinstance(operations, ImageOperationData):
        raise TypeError("operations must be ImageOperationData")
    return MetadataCleanupOptions(
        remove_exif=operations.remove_exif,
        remove_xmp=operations.remove_xmp,
        remove_iptc=operations.remove_iptc,
        remove_comments_text=operations.remove_comments_text,
        remove_embedded_thumbnail=operations.remove_embedded_thumbnail,
        remove_generator_fields=operations.remove_generator_fields,
        preserve_icc=operations.preserve_icc,
        preserve_dpi=operations.preserve_dpi,
        remove_embedded_c2pa=operations.remove_embedded_c2pa,
    )


def _record_for_file(
    state: ProjectState,
    file_path: str,
    *,
    create: bool = False,
) -> VerificationRecordData:
    if state.mode is not ProjectMode.PROCESSING:
        raise EvidenceCenterError(
            "Центр проверки доступен только в режиме обработки"
        )
    if file_path not in state.processing.selected_files:
        raise EvidenceCenterError("Файл не входит в текущий проект")
    for record in state.processing.verification_records:
        if record.file_path == file_path:
            return record
    record = VerificationRecordData(file_path=file_path)
    if create:
        state.processing.verification_records.append(record)
    return record


def set_verification_result(
    state: ProjectState,
    file_path: str,
    provider: str,
    status: str,
    stage: str = "input",
) -> VerificationRecordData:
    if provider not in {"synthid", "openai"}:
        raise EvidenceCenterError("Неизвестный источник проверки")
    if status not in {
        "detected",
        "not_detected",
        "not_verified",
        "unsupported",
    }:
        raise EvidenceCenterError("Неизвестный статус проверки")
    normalized_stage = stage if status in _CHECKED_STATUSES else "not_checked"
    if normalized_stage not in {"not_checked", "input", "output"}:
        raise EvidenceCenterError("Неизвестный этап проверки")
    record = _record_for_file(state, file_path, create=True)
    setattr(record, f"{provider}_status", status)
    setattr(record, f"{provider}_stage", normalized_stage)
    record.__post_init__()
    return record


def _file_hint_status(
    inspection: dict[str, Any],
) -> tuple[FileHintStatus, FileHintStatus]:
    if inspection.get("status") != "ok":
        return FileHintStatus.UNKNOWN, FileHintStatus.UNKNOWN
    categories = inspection.get("categories", {})
    metadata_present = any(
        bool(categories.get(name, {}).get("present"))
        for name in (
            "exif",
            "xmp",
            "iptc",
            "comments_text",
            "embedded_thumbnail",
            "generator_fields",
        )
    )
    c2pa_presence = inspection.get("c2pa", {}).get("presence", "unknown")
    c2pa_hint = {
        "present": FileHintStatus.PRESENT,
        "not_present": FileHintStatus.NOT_PRESENT,
    }.get(str(c2pa_presence), FileHintStatus.UNKNOWN)
    return (
        FileHintStatus.PRESENT
        if metadata_present
        else FileHintStatus.NOT_PRESENT,
        c2pa_hint,
    )


def _pixel_report(
    *,
    marker_type: PixelMarkerType,
    status: str,
    stage: str,
    source: PixelEvidenceSource,
    metadata_hint: FileHintStatus,
    c2pa_hint: FileHintStatus,
) -> dict[str, Any]:
    checked = status in _CHECKED_STATUSES
    return create_pixel_watermark_status(
        marker_type=marker_type,
        evidence_status=PixelEvidenceStatus(status),
        evidence_source=source if checked else PixelEvidenceSource.NONE,
        evidence_stage=(
            PixelEvidenceStage(stage)
            if checked
            else PixelEvidenceStage.NOT_CHECKED
        ),
        metadata_hint=metadata_hint,
        c2pa_hint=c2pa_hint,
    )


def _safe_category_summary(
    inspection: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    categories = inspection.get("categories", {})
    return {
        name: {
            "present": bool(categories.get(name, {}).get("present")),
            "item_count": max(
                0,
                int(categories.get(name, {}).get("item_count", 0)),
            ),
            "size_bytes": max(
                0,
                int(categories.get(name, {}).get("size_bytes", 0)),
            ),
        }
        for name in (
            "exif",
            "xmp",
            "iptc",
            "comments_text",
            "embedded_thumbnail",
            "generator_fields",
            "icc_profile",
            "dpi",
        )
    }


def build_evidence_report(
    state: ProjectState,
    file_path: str,
    *,
    rights_confirmed: bool,
) -> dict[str, Any]:
    if not rights_confirmed:
        raise EvidenceCenterError("Подтвердите право обрабатывать выбранный файл")
    record = _record_for_file(state, file_path)
    inspection = inspect_image_metadata(file_path)
    metadata_hint, c2pa_hint = _file_hint_status(inspection)
    synthid = _pixel_report(
        marker_type=PixelMarkerType.SYNTHID,
        status=record.synthid_status,
        stage=record.synthid_stage,
        source=PixelEvidenceSource.OFFICIAL_SYNTHID,
        metadata_hint=metadata_hint,
        c2pa_hint=c2pa_hint,
    )

    c2pa = inspection.get("c2pa", {})
    file_index = state.processing.selected_files.index(file_path) + 1
    options = cleanup_options_from_operations(state.processing.operations)
    return {
        "schema_version": 1,
        "file": {
            "index": file_index,
            "display_name": Path(file_path).name,
        },
        "processing": {"status": "not_run", "claim": "processing_not_run"},
        "file_hints": {
            "inspection_status": str(inspection.get("status", "invalid")),
            "metadata": metadata_hint.value,
            "c2pa": c2pa_hint.value,
            "affects_pixel_evidence": False,
            "categories": _safe_category_summary(inspection),
            "c2pa_summary": {
                "presence": str(c2pa.get("presence", "unknown")),
                "embedded_presence": str(
                    c2pa.get("embedded_presence", "unknown")
                ),
                "embedded_reference_presence": str(
                    c2pa.get("embedded_reference_presence", "unknown")
                ),
                "external_reference_presence": str(
                    c2pa.get("external_reference_presence", "unknown")
                ),
                "validation": str(c2pa.get("validation", "not_validated")),
                "scan_status": str(c2pa.get("scan_status", "not_scanned")),
            },
        },
        "pixel_evidence": {
            "synthid": synthid["pixel_evidence"],
        },
        "verification_handoff": {
            "gemini": {
                "method": "official_gemini",
                "tool_url": GEMINI_VERIFY_URL,
                "documentation_url": GEMINI_HELP_URL,
                "auto_upload": False,
                "recorded_status": record.synthid_status,
                "recorded_stage": record.synthid_stage,
            },
            "openai": {
                "method": "official_openai_verify",
                "tool_url": OPENAI_VERIFY_URL,
                "auto_upload": False,
                "recorded_status": record.openai_status,
                "recorded_stage": record.openai_stage,
                "interpretation": (
                    "supported_openai_signal_detected"
                    if record.openai_status == "detected"
                    else (
                        "supported_openai_signal_not_detected"
                        if record.openai_status == "not_detected"
                        else "openai_verification_not_conclusive"
                    )
                ),
                "signal_type": "not_inferred",
                "human_origin_claim": "not_inferred",
                "removal_claim": "not_claimed",
            },
        },
        "cleanup_plan": {
            field: bool(getattr(options, field))
            for field in options.__dataclass_fields__
        },
    }


def format_evidence_log(report: dict[str, Any]) -> str:
    file_hints = report.get("file_hints", {})
    synthid = report.get("pixel_evidence", {}).get("synthid", {})
    openai = report.get("verification_handoff", {}).get("openai", {})
    allowed_hint = {"present", "not_present", "unknown", "not_checked"}
    allowed_evidence = {
        "detected",
        "not_detected",
        "not_verified",
        "unsupported",
    }
    metadata = str(file_hints.get("metadata", "unknown"))
    c2pa = str(file_hints.get("c2pa", "unknown"))
    synthid_status = str(synthid.get("status", "not_verified"))
    openai_status = str(openai.get("recorded_status", "not_verified"))
    if metadata not in allowed_hint:
        metadata = "unknown"
    if c2pa not in allowed_hint:
        c2pa = "unknown"
    if synthid_status not in allowed_evidence:
        synthid_status = "not_verified"
    if openai_status not in allowed_evidence:
        openai_status = "not_verified"
    return (
        f"evidence metadata={metadata}; c2pa={c2pa}; "
        f"synthid={synthid_status}; openai={openai_status}; "
        "human_origin=not_inferred; removal=not_claimed"
    )


def export_evidence_report(
    state: ProjectState,
    file_path: str,
    destination: str | os.PathLike[str],
    *,
    rights_confirmed: bool,
) -> dict[str, Any]:
    report = build_evidence_report(
        state,
        file_path,
        rights_confirmed=rights_confirmed,
    )
    target = Path(destination)
    if target.suffix.casefold() != ".json":
        raise EvidenceCenterError("Отчёт должен иметь расширение .json")
    if not target.parent.is_dir():
        raise EvidenceCenterError("Папка отчёта не существует")
    payload = json.dumps(
        report,
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    ).encode("utf-8")
    if len(payload) > MAX_EVIDENCE_REPORT_BYTES:
        raise EvidenceCenterError("Отчёт превышает допустимый размер")
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=target.parent,
            prefix=f".{target.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            temporary_path = Path(temporary.name)
            temporary.write(payload)
            temporary.flush()
            os.fsync(temporary.fileno())
        os.replace(temporary_path, target)
        temporary_path = None
    except OSError as error:
        raise EvidenceCenterError("Не удалось безопасно сохранить отчёт") from error
    finally:
        if temporary_path is not None:
            try:
                temporary_path.unlink(missing_ok=True)
            except OSError:
                pass
    return report


def _default_url_opener(url: str) -> bool:
    return bool(QDesktopServices.openUrl(QUrl(url)))


class EvidenceCenterPage(QScrollArea):
    def __init__(
        self,
        state: ProjectState,
        changed: Callable[[], None],
        *,
        tokens: V3DesignTokens = DEFAULT_TOKENS,
        url_opener: Callable[[str], bool] | None = None,
        inspection_authorized: Callable[[], bool] | None = None,
    ) -> None:
        super().__init__()
        self.state = state
        self.changed = changed
        self.tokens = tokens
        self.url_opener = url_opener or _default_url_opener
        self.inspection_authorized = inspection_authorized or (lambda: False)
        self.setWidgetResizable(True)

        content = QWidget()
        self.content_layout = QVBoxLayout(content)
        self.content_layout.setContentsMargins(
            tokens.space_4,
            tokens.space_4,
            tokens.space_4,
            tokens.space_4,
        )
        self.content_layout.setSpacing(tokens.space_4)
        self.setWidget(content)

        title = QLabel("Проверка и очистка")
        title.setProperty("v3Title", True)
        self.content_layout.addWidget(title)
        description = QLabel(
            "Данные файла, Content Credentials и пиксельные свидетельства "
            "показываются независимо."
        )
        description.setWordWrap(True)
        description.setProperty("v3Description", True)
        self.content_layout.addWidget(description)

        self.file_combo = QComboBox()
        self.file_combo.currentIndexChanged.connect(self._file_changed)
        self.content_layout.addWidget(self.file_combo)

        self.file_card = EvidenceCard(
            "Данные файла",
            "Локальная проверка EXIF, XMP, IPTC и generator fields без показа значений.",
            tokens=tokens,
        )
        self.cleanup_widgets: dict[str, QCheckBox] = {}
        for field, label in (
            ("remove_exif", "Удалить EXIF"),
            ("remove_xmp", "Удалить XMP"),
            ("remove_iptc", "Удалить IPTC"),
            ("remove_comments_text", "Удалить comments/text"),
            ("remove_embedded_thumbnail", "Удалить embedded thumbnail"),
            ("remove_generator_fields", "Удалить generator fields"),
        ):
            checkbox = QCheckBox(label)
            checkbox.toggled.connect(
                lambda checked, name=field: self._cleanup_changed(name, checked)
            )
            self.cleanup_widgets[field] = checkbox
            self.file_card.add_widget(checkbox)
        self.content_layout.addWidget(self.file_card)

        self.c2pa_card = EvidenceCard(
            "Content Credentials",
            "Наличие C2PA — file-level hint; подпись здесь не валидируется.",
            tokens=tokens,
        )
        self.remove_c2pa_checkbox = QCheckBox(
            "Удалить embedded C2PA и выбранные ссылки при обработке"
        )
        self.remove_c2pa_checkbox.toggled.connect(
            lambda checked: self._cleanup_changed(
                "remove_embedded_c2pa",
                checked,
            )
        )
        self.c2pa_card.add_widget(self.remove_c2pa_checkbox)
        self.content_layout.addWidget(self.c2pa_card)

        self.pixel_card = EvidenceCard(
            "Пиксельные маркеры",
            "Gemini используется только для ручной записи результата SynthID. "
            "Приложение не загружает файл.",
            tokens=tokens,
        )
        self.synthid_status, self.synthid_stage = self._handoff_row(
            "Gemini / SynthID",
            GEMINI_VERIFY_URL,
            "synthid",
            self.pixel_card.content_layout,
        )
        self.scope_warning = QLabel(
            "«Не обнаружено» означает только отсутствие SynthID в выбранной "
            "проверке и не доказывает человеческое происхождение."
        )
        self.scope_warning.setWordWrap(True)
        self.scope_warning.setProperty("state", "warning")
        self.pixel_card.add_widget(self.scope_warning)
        self.content_layout.addWidget(self.pixel_card)

        self.openai_handoff_group = QGroupBox(
            "Официальный OpenAI handoff — не pixel evidence"
        )
        openai_layout = QVBoxLayout(self.openai_handoff_group)
        openai_description = QLabel(
            "OpenAI Verify может сообщить о C2PA, SynthID или другом "
            "поддерживаемом сигнале. Без типа сигнала результат не относится "
            "ни к C2PA, ни к pixel evidence. Файл загружается только вручную."
        )
        openai_description.setWordWrap(True)
        openai_layout.addWidget(openai_description)
        self.openai_status_label = QLabel()
        self.openai_status_label.setWordWrap(True)
        openai_layout.addWidget(self.openai_status_label)
        self.openai_status, self.openai_stage = self._handoff_row(
            "OpenAI Verify / общий provenance signal",
            OPENAI_VERIFY_URL,
            "openai",
            openai_layout,
        )
        self.content_layout.addWidget(self.openai_handoff_group)

        export_row = QWidget()
        export_layout = QHBoxLayout(export_row)
        export_layout.setContentsMargins(0, 0, 0, 0)
        self.export_button = V3Button(
            "Экспортировать отчёт",
            ButtonVariant.SECONDARY,
        )
        self.export_button.clicked.connect(self._choose_report_path)
        export_layout.addWidget(self.export_button)
        self.action_status = QLabel()
        self.action_status.setWordWrap(True)
        export_layout.addWidget(self.action_status, 1)
        self.content_layout.addWidget(export_row)
        self.content_layout.addStretch(1)
        self.refresh_from_state()

    def _handoff_row(
        self,
        label: str,
        url: str,
        provider: str,
        container: QVBoxLayout,
    ) -> tuple[QComboBox, QComboBox]:
        group = QGroupBox(label)
        layout = QVBoxLayout(group)
        button = V3Button(
            f"Открыть {label}",
            ButtonVariant.SECONDARY,
        )
        button.clicked.connect(
            lambda: self._open_official_service(url)
        )
        layout.addWidget(button)
        status = QComboBox()
        for item_label, value in _RECORDED_STATUSES:
            status.addItem(item_label, value)
        stage = QComboBox()
        for item_label, value in _RECORDED_STAGES:
            stage.addItem(item_label, value)
        status.currentIndexChanged.connect(
            lambda _index, name=provider: self._result_changed(name)
        )
        stage.currentIndexChanged.connect(
            lambda _index, name=provider: self._result_changed(name)
        )
        layout.addWidget(status)
        layout.addWidget(stage)
        container.addWidget(group)
        return status, stage

    def _current_path(self) -> str:
        value = self.file_combo.currentData()
        return str(value or "")

    def _file_changed(self) -> None:
        self._refresh_cards()

    def _cleanup_changed(self, field: str, checked: bool) -> None:
        setattr(self.state.processing.operations, field, bool(checked))
        self.state.processing.recipe = "custom"
        self.changed()
        self._refresh_cards()

    @staticmethod
    def _set_combo(combo: QComboBox, value: str) -> None:
        index = combo.findData(value)
        if index >= 0:
            combo.setCurrentIndex(index)

    def _result_changed(self, provider: str) -> None:
        file_path = self._current_path()
        if not file_path:
            return
        if not bool(self.inspection_authorized()):
            self.action_status.setText(
                "Сначала подтвердите право обрабатывать файл на шаге C1."
            )
            return
        status_combo = (
            self.synthid_status
            if provider == "synthid"
            else self.openai_status
        )
        stage_combo = (
            self.synthid_stage
            if provider == "synthid"
            else self.openai_stage
        )
        status = str(status_combo.currentData())
        stage_combo.setEnabled(status in _CHECKED_STATUSES)
        set_verification_result(
            self.state,
            file_path,
            provider,
            status,
            str(stage_combo.currentData()),
        )
        self.changed()
        self._refresh_pixel_status()

    def _open_official_service(self, url: str) -> None:
        try:
            opened = bool(self.url_opener(url))
        except Exception:
            opened = False
        self.action_status.setText(
            "Официальный сервис открыт. Файл не передан."
            if opened
            else "Не удалось открыть официальный сервис. Файл не передан."
        )

    def _choose_report_path(self) -> None:
        file_path = self._current_path()
        if not file_path:
            self.action_status.setText("Сначала выберите файл.")
            return
        if not bool(self.inspection_authorized()):
            self.action_status.setText(
                "Сначала подтвердите право обрабатывать файл на шаге C1."
            )
            return
        destination, _ = QFileDialog.getSaveFileName(
            self,
            "Сохранить evidence report",
            "evidence-report.json",
            "JSON (*.json)",
        )
        if not destination:
            return
        try:
            export_evidence_report(
                self.state,
                file_path,
                destination,
                rights_confirmed=bool(self.inspection_authorized()),
            )
        except (EvidenceCenterError, OSError, TypeError, ValueError):
            self.action_status.setText("Не удалось экспортировать отчёт.")
            return
        self.action_status.setText("Отчёт экспортирован.")

    def _refresh_pixel_status(self) -> None:
        file_path = self._current_path()
        if not file_path:
            self.pixel_card.set_status("Файл не выбран.", warning=True)
            self.openai_status_label.setText("Файл не выбран.")
            return
        record = _record_for_file(self.state, file_path)
        self.pixel_card.set_status(
            "SynthID: "
            + record.synthid_status
            + " · human_origin=not_inferred · removal=not_claimed",
            warning=record.synthid_status == "not_detected",
        )
        self.openai_status_label.setText(
            "Handoff OpenAI: "
            + record.openai_status
            + " · signal_type=not_inferred · не pixel evidence · "
            "human_origin=not_inferred · removal=not_claimed"
        )

    def _refresh_cards(self) -> None:
        file_path = self._current_path()
        if not file_path:
            self.file_card.set_status("Файл не выбран.", warning=True)
            self.c2pa_card.set_status("Файл не выбран.", warning=True)
            self._refresh_pixel_status()
            return
        if not bool(self.inspection_authorized()):
            message = "Сначала подтвердите право обрабатывать файл на шаге C1."
            self.file_card.set_status(message, warning=True)
            self.c2pa_card.set_status("Локальная проверка ещё не запускалась.", warning=True)
            self.pixel_card.set_status("Пиксельная проверка ещё не записана.", warning=True)
            self.openai_status_label.setText(
                "OpenAI handoff ещё не записан; это не pixel evidence."
            )
            return
        inspection = inspect_image_metadata(file_path)
        if inspection.get("status") != "ok":
            self.file_card.set_status(
                "Файл не поддерживается локальным inspector.",
                warning=True,
            )
            self.c2pa_card.set_status(
                "C2PA не классифицирован.",
                warning=True,
            )
        else:
            categories = inspection.get("categories", {})
            present = [
                name
                for name in (
                    "exif",
                    "xmp",
                    "iptc",
                    "comments_text",
                    "embedded_thumbnail",
                    "generator_fields",
                )
                if categories.get(name, {}).get("present")
            ]
            self.file_card.set_status(
                "Обнаружено: " + (", ".join(present) if present else "нет")
            )
            c2pa = inspection.get("c2pa", {})
            self.c2pa_card.set_status(
                "Наличие: "
                + str(c2pa.get("presence", "unknown"))
                + " · scan: "
                + str(c2pa.get("scan_status", "not_scanned"))
                + " · validation: "
                + str(c2pa.get("validation", "not_validated")),
                warning=c2pa.get("presence") == "unknown",
            )
        record = _record_for_file(self.state, file_path)
        for combo, value in (
            (self.synthid_status, record.synthid_status),
            (self.synthid_stage, record.synthid_stage),
            (self.openai_status, record.openai_status),
            (self.openai_stage, record.openai_stage),
        ):
            combo.blockSignals(True)
            self._set_combo(
                combo,
                value if value != "not_checked" else "input",
            )
            combo.blockSignals(False)
        self.synthid_stage.setEnabled(
            record.synthid_status in _CHECKED_STATUSES
        )
        self.openai_stage.setEnabled(
            record.openai_status in _CHECKED_STATUSES
        )
        operations = self.state.processing.operations
        for field, checkbox in self.cleanup_widgets.items():
            checkbox.blockSignals(True)
            checkbox.setChecked(bool(getattr(operations, field)))
            checkbox.blockSignals(False)
        self.remove_c2pa_checkbox.blockSignals(True)
        self.remove_c2pa_checkbox.setChecked(
            operations.remove_embedded_c2pa
        )
        self.remove_c2pa_checkbox.blockSignals(False)
        self._refresh_pixel_status()

    def validation_issues(self) -> tuple[str, ...]:
        if self.state.processing.selected_files and not bool(
            self.inspection_authorized()
        ):
            return ("file_rights_confirmation_required",)
        return ()
    def refresh_from_state(self) -> None:
        selected_path = self._current_path()
        self.file_combo.blockSignals(True)
        self.file_combo.clear()
        for file_path in self.state.processing.selected_files:
            self.file_combo.addItem(Path(file_path).name, file_path)
        if selected_path:
            index = self.file_combo.findData(selected_path)
            if index >= 0:
                self.file_combo.setCurrentIndex(index)
        self.file_combo.blockSignals(False)
        self._refresh_cards()
