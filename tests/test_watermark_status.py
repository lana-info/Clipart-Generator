import json
import unittest

from watermark_status import (
    FileHintStatus,
    PixelEvidenceSource,
    PixelEvidenceStage,
    PixelEvidenceStatus,
    PixelMarkerType,
    PixelProcessingStatus,
    create_pixel_watermark_status,
    format_pixel_watermark_status,
)


class WatermarkStatusTests(unittest.TestCase):
    def test_not_detected_is_scoped_and_never_proves_human_origin(self):
        report = create_pixel_watermark_status(
            marker_type=PixelMarkerType.SYNTHID,
            evidence_status=PixelEvidenceStatus.NOT_DETECTED,
            evidence_source=PixelEvidenceSource.OFFICIAL_SYNTHID,
            evidence_stage=PixelEvidenceStage.OUTPUT,
        )

        self.assertEqual(report["pixel_evidence"]["status"], "not_detected")
        self.assertEqual(report["pixel_evidence"]["stage"], "output")
        self.assertEqual(
            report["pixel_evidence"]["interpretation"],
            "marker_not_detected_by_selected_check",
        )
        self.assertEqual(report["pixel_evidence"]["human_origin_claim"], "not_inferred")
        self.assertEqual(report["pixel_evidence"]["removal_claim"], "not_claimed")

    def test_processing_success_is_separate_from_unverified_evidence(self):
        report = create_pixel_watermark_status(
            marker_type="synthid",
            processing_status=PixelProcessingStatus.SUCCEEDED,
        )

        self.assertEqual(report["processing"]["status"], "succeeded")
        self.assertEqual(report["processing"]["claim"], "processing_completed")
        self.assertEqual(report["pixel_evidence"]["status"], "not_verified")
        self.assertEqual(report["pixel_evidence"]["removal_claim"], "not_claimed")
        self.assertTrue(report["verification_handoff"]["required"])
        self.assertEqual(report["verification_handoff"]["method"], "official_gemini")

    def test_metadata_and_c2pa_hints_never_become_pixel_evidence(self):
        report = create_pixel_watermark_status(
            metadata_hint=FileHintStatus.PRESENT,
            c2pa_hint=FileHintStatus.PRESENT,
        )

        self.assertEqual(report["file_hints"]["metadata"], "present")
        self.assertEqual(report["file_hints"]["c2pa"], "present")
        self.assertFalse(report["file_hints"]["affects_pixel_evidence"])
        self.assertEqual(report["pixel_evidence"]["status"], "not_verified")

    def test_unknown_marker_uses_manual_handoff_without_removed_status(self):
        report = create_pixel_watermark_status(
            marker_type=PixelMarkerType.UNKNOWN,
            evidence_status=PixelEvidenceStatus.UNSUPPORTED,
            processing_status=PixelProcessingStatus.SUCCEEDED,
        )

        self.assertEqual(report["verification_handoff"]["method"], "manual_review")
        self.assertNotIn("removed", {item.value for item in PixelEvidenceStatus})
        self.assertEqual(report["pixel_evidence"]["removal_claim"], "not_claimed")

    def test_detector_evidence_requires_a_compatible_source(self):
        with self.assertRaisesRegex(ValueError, "requires a detector source"):
            create_pixel_watermark_status(evidence_status="detected", evidence_stage="output")
        with self.assertRaisesRegex(ValueError, "requires input or output stage"):
            create_pixel_watermark_status(
                evidence_status="detected",
                evidence_source="external_detector",
            )
        with self.assertRaisesRegex(ValueError, "cannot claim a detector source"):
            create_pixel_watermark_status(
                evidence_status="not_verified",
                evidence_source="external_detector",
            )
        with self.assertRaisesRegex(ValueError, "cannot claim an evidence stage"):
            create_pixel_watermark_status(
                evidence_status="unsupported",
                evidence_stage="input",
            )
        with self.assertRaisesRegex(ValueError, "marker_type=synthid"):
            create_pixel_watermark_status(
                marker_type="unknown",
                evidence_status="detected",
                evidence_source="official_synthid",
                evidence_stage="input",
            )

    def test_safe_log_ignores_untrusted_extra_values_and_is_serializable(self):
        report = create_pixel_watermark_status(
            marker_type="synthid",
            processing_status="failed",
        )
        report["provider_message"] = "SECRET_API_KEY_VALUE"
        report["pixel_evidence"]["raw_response"] = "SECRET_API_KEY_VALUE"

        log_line = format_pixel_watermark_status(report)

        self.assertNotIn("SECRET_API_KEY_VALUE", log_line)
        self.assertIn("обработка=ошибка", log_line)
        self.assertIn("удаление=не заявлено", log_line)
        json.dumps(report, ensure_ascii=False)


if __name__ == "__main__":
    unittest.main()
