from v3_processing_flow import operation_validation_issues
from v3_clipart_flow import _safe_runtime_error
from v3_project_state import ImageOperationData


def test_local_processing_does_not_require_deep_watermark_consent():
    operations = ImageOperationData(unsharp=True)
    assert operation_validation_issues(operations, allow_full_image_changes=False) == ()


def test_deep_watermark_requires_its_own_consent():
    operations = ImageOperationData(invisible_watermark_cleanup=True)
    assert operation_validation_issues(operations, allow_full_image_changes=False) == (
        "deep_watermark_consent_required",
    )


def test_access_denied_has_user_facing_message():
    error = PermissionError(5, "Access is denied")
    assert "Нет доступа" in _safe_runtime_error(error)
