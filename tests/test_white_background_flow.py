"""Local provider validation and secret-free run-plan contracts."""
from unittest.mock import patch

import pytest
from PIL import Image

from v3_processing_flow import (
    ProcessingFlowError, build_processing_run_request, estimate_processing_cost,
    operation_validation_issues, uses_external_processing, validate_processing_providers,
)
from v3_project_state import ImageOperationData, ProjectMode, ProjectState
from v3_provider_registry import processing_provider_options, provider_spec


def white_operations():
    return ImageOperationData(
        upscale_before=False, remove_background=True,
        remove_background_provider="local_white_background",
    )


def test_registry_exposes_only_local_free_keyless_background_operation():
    spec = provider_spec("local_white_background")
    assert spec.label == "Белый фон · чёткий контур"
    assert spec.operations == ("remove_background",)
    assert not spec.requires_network
    assert not spec.requires_cost
    assert not spec.requires_api_key
    assert spec.preserves_alpha
    assert spec.visible_controls == ()
    assert (spec.label, spec.provider_id) in processing_provider_options("remove_background_provider")
    assert not uses_external_processing(white_operations())
    for field in ("upscale_before_provider", "upscale_after_provider"):
        assert spec.provider_id not in dict(processing_provider_options(field)).values()


@pytest.mark.parametrize("available", [True, False])
def test_availability_only_blocks_active_white_method(available):
    operations = white_operations()
    with patch("white_background.white_background_available", return_value=available):
        expected = () if available else ("white_background_unavailable",)
        assert operation_validation_issues(operations, allow_full_image_changes=False) == expected
        if available:
            validate_processing_providers(operations)
        else:
            with pytest.raises(ProcessingFlowError, match="локальная модель U2Net"):
                validate_processing_providers(operations)
        operations.remove_background = False
        operations.trim = True
        validate_processing_providers(operations)
        assert operation_validation_issues(operations, allow_full_image_changes=False) == ()


def test_local_run_plan_roundtrip_keeps_white_method_without_keys_or_transfer_consent(tmp_path):
    source = tmp_path / "white.png"
    Image.new("RGB", (12, 12), "white").save(source)
    state = ProjectState(mode=ProjectMode.PROCESSING)
    state.common.work_dir = str(tmp_path)
    state.processing.selected_files = [str(source)]
    state.processing.operations = white_operations()
    state = ProjectState.from_dict(state.to_dict())
    with patch("white_background.white_background_available", return_value=True):
        request = build_processing_run_request(
            state, {}, allow_full_image_changes=False, external_transfer_consent=False,
        )
    assert request.settings["remove_bg_provider"] == "local_white_background"
    assert not any("api_key" in key for key in request.settings)
    cost = estimate_processing_cost(state.processing.operations, 1)
    assert cost == "локально, без оплаты API"


def test_request_rejects_white_method_before_runtime_when_cache_is_missing(tmp_path):
    source = tmp_path / "white.png"
    Image.new("RGB", (12, 12), "white").save(source)
    state = ProjectState(mode=ProjectMode.PROCESSING)
    state.common.work_dir = str(tmp_path)
    state.processing.selected_files = [str(source)]
    state.processing.operations = white_operations()
    with patch("white_background.white_background_available", return_value=False):
        with pytest.raises(ProcessingFlowError, match="U2Net"):
            build_processing_run_request(
                state, {}, allow_full_image_changes=False, external_transfer_consent=False,
            )
