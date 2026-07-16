"""Structured, claim-safe status contract for hidden pixel watermarks."""

from __future__ import annotations

from enum import Enum
from typing import Any


SCHEMA_VERSION = 1


class PixelMarkerType(str, Enum):
    SYNTHID = "synthid"
    UNKNOWN = "unknown"


class PixelEvidenceStatus(str, Enum):
    DETECTED = "detected"
    NOT_DETECTED = "not_detected"
    NOT_VERIFIED = "not_verified"
    UNSUPPORTED = "unsupported"


class PixelEvidenceSource(str, Enum):
    NONE = "none"
    OFFICIAL_SYNTHID = "official_synthid"
    EXTERNAL_DETECTOR = "external_detector"


class PixelEvidenceStage(str, Enum):
    NOT_CHECKED = "not_checked"
    INPUT = "input"
    OUTPUT = "output"


class PixelProcessingStatus(str, Enum):
    NOT_RUN = "not_run"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class FileHintStatus(str, Enum):
    NOT_CHECKED = "not_checked"
    PRESENT = "present"
    NOT_PRESENT = "not_present"
    UNKNOWN = "unknown"


class VerificationHandoff(str, Enum):
    NONE = "none"
    OFFICIAL_GEMINI = "official_gemini"
    MANUAL_REVIEW = "manual_review"


_EVIDENCE_INTERPRETATION = {
    PixelEvidenceStatus.DETECTED: "marker_detected_by_selected_check",
    PixelEvidenceStatus.NOT_DETECTED: "marker_not_detected_by_selected_check",
    PixelEvidenceStatus.NOT_VERIFIED: "pixel_marker_not_verified",
    PixelEvidenceStatus.UNSUPPORTED: "pixel_marker_verification_unsupported",
}

_PROCESSING_CLAIM = {
    PixelProcessingStatus.NOT_RUN: "processing_not_run",
    PixelProcessingStatus.SUCCEEDED: "processing_completed",
    PixelProcessingStatus.FAILED: "processing_failed",
    PixelProcessingStatus.CANCELLED: "processing_cancelled",
}

_HANDOFF_INSTRUCTION = {
    VerificationHandoff.NONE: "none",
    VerificationHandoff.OFFICIAL_GEMINI: "verify_one_file_with_gemini_synthid",
    VerificationHandoff.MANUAL_REVIEW: "record_external_or_manual_verification",
}


def _enum_value(enum_type, value, field_name):
    if isinstance(value, enum_type):
        return value
    try:
        return enum_type(str(value))
    except ValueError as error:
        allowed = ", ".join(item.value for item in enum_type)
        raise ValueError(f"Unsupported {field_name}; expected one of: {allowed}") from error


def _verification_handoff(marker_type, evidence_status):
    if evidence_status in {
        PixelEvidenceStatus.DETECTED,
        PixelEvidenceStatus.NOT_DETECTED,
    }:
        return VerificationHandoff.NONE
    if marker_type is PixelMarkerType.SYNTHID:
        return VerificationHandoff.OFFICIAL_GEMINI
    return VerificationHandoff.MANUAL_REVIEW


def create_pixel_watermark_status(
    *,
    marker_type=PixelMarkerType.UNKNOWN,
    evidence_status=PixelEvidenceStatus.NOT_VERIFIED,
    evidence_source=PixelEvidenceSource.NONE,
    evidence_stage=PixelEvidenceStage.NOT_CHECKED,
    processing_status=PixelProcessingStatus.NOT_RUN,
    metadata_hint=FileHintStatus.NOT_CHECKED,
    c2pa_hint=FileHintStatus.NOT_CHECKED,
) -> dict[str, Any]:
    """Create a JSON-compatible report without making a removal/origin claim."""
    marker_type = _enum_value(PixelMarkerType, marker_type, "marker_type")
    evidence_status = _enum_value(PixelEvidenceStatus, evidence_status, "evidence_status")
    evidence_source = _enum_value(PixelEvidenceSource, evidence_source, "evidence_source")
    evidence_stage = _enum_value(PixelEvidenceStage, evidence_stage, "evidence_stage")
    processing_status = _enum_value(PixelProcessingStatus, processing_status, "processing_status")
    metadata_hint = _enum_value(FileHintStatus, metadata_hint, "metadata_hint")
    c2pa_hint = _enum_value(FileHintStatus, c2pa_hint, "c2pa_hint")

    has_detector_result = evidence_status in {
        PixelEvidenceStatus.DETECTED,
        PixelEvidenceStatus.NOT_DETECTED,
    }
    if has_detector_result and evidence_source is PixelEvidenceSource.NONE:
        raise ValueError("Detected/not-detected evidence requires a detector source")
    if has_detector_result and evidence_stage is PixelEvidenceStage.NOT_CHECKED:
        raise ValueError("Detected/not-detected evidence requires input or output stage")
    if not has_detector_result and evidence_source is not PixelEvidenceSource.NONE:
        raise ValueError("Unverified/unsupported evidence cannot claim a detector source")
    if not has_detector_result and evidence_stage is not PixelEvidenceStage.NOT_CHECKED:
        raise ValueError("Unverified/unsupported evidence cannot claim an evidence stage")
    if (
        marker_type is PixelMarkerType.UNKNOWN
        and evidence_source is PixelEvidenceSource.OFFICIAL_SYNTHID
    ):
        raise ValueError("Official SynthID evidence must use marker_type=synthid")

    handoff = _verification_handoff(marker_type, evidence_status)
    return {
        "schema_version": SCHEMA_VERSION,
        "marker_type": marker_type.value,
        "processing": {
            "status": processing_status.value,
            "claim": _PROCESSING_CLAIM[processing_status],
        },
        "pixel_evidence": {
            "status": evidence_status.value,
            "source": evidence_source.value,
            "stage": evidence_stage.value,
            "interpretation": _EVIDENCE_INTERPRETATION[evidence_status],
            "human_origin_claim": "not_inferred",
            "removal_claim": "not_claimed",
        },
        "file_hints": {
            "metadata": metadata_hint.value,
            "c2pa": c2pa_hint.value,
            "affects_pixel_evidence": False,
        },
        "verification_handoff": {
            "required": handoff is not VerificationHandoff.NONE,
            "method": handoff.value,
            "instruction_code": _HANDOFF_INSTRUCTION[handoff],
        },
    }


def format_pixel_watermark_status(report: dict[str, Any]) -> str:
    """Format only controlled status fields; never echo provider/user values."""
    marker_type = _enum_value(PixelMarkerType, report.get("marker_type"), "marker_type")
    processing_status = _enum_value(
        PixelProcessingStatus,
        report.get("processing", {}).get("status"),
        "processing_status",
    )
    evidence_status = _enum_value(
        PixelEvidenceStatus,
        report.get("pixel_evidence", {}).get("status"),
        "evidence_status",
    )
    handoff = _enum_value(
        VerificationHandoff,
        report.get("verification_handoff", {}).get("method"),
        "verification_handoff",
    )

    marker_labels = {
        PixelMarkerType.SYNTHID: "SynthID",
        PixelMarkerType.UNKNOWN: "неизвестная",
    }
    processing_labels = {
        PixelProcessingStatus.NOT_RUN: "не запускалась",
        PixelProcessingStatus.SUCCEEDED: "выполнена",
        PixelProcessingStatus.FAILED: "ошибка",
        PixelProcessingStatus.CANCELLED: "отменена",
    }
    evidence_labels = {
        PixelEvidenceStatus.DETECTED: "обнаружена выбранной проверкой",
        PixelEvidenceStatus.NOT_DETECTED: "не обнаружена выбранной проверкой",
        PixelEvidenceStatus.NOT_VERIFIED: "не проверялась",
        PixelEvidenceStatus.UNSUPPORTED: "проверка не поддерживается",
    }
    handoff_labels = {
        VerificationHandoff.NONE: "не требуется",
        VerificationHandoff.OFFICIAL_GEMINI: "официальная проверка Gemini",
        VerificationHandoff.MANUAL_REVIEW: "внешняя или ручная проверка",
    }
    return (
        f"Пиксельная метка: тип={marker_labels[marker_type]}; "
        f"обработка={processing_labels[processing_status]}; "
        f"свидетельство={evidence_labels[evidence_status]}; "
        f"следующий шаг={handoff_labels[handoff]}; удаление=не заявлено"
    )
