from runtime_settings import (
    build_runtime_settings,
    normalize_provider_concurrency,
    normalize_api_concurrency,
)


def test_runtime_settings_snapshot_merges_secrets_without_mutating_config():
    config = {"timeout": 60, "kie_api_key": "legacy"}
    result = build_runtime_settings(config, {"kie_api_key": " fresh "})
    assert result["kie_api_key"] == "fresh"
    assert config["kie_api_key"] == "legacy"


def test_runtime_settings_snapshot_includes_runpod_credentials():
    result = build_runtime_settings(
        {}, {"runpod_api_key": "key", "runpod_endpoint_id": "endpoint"}
    )
    assert result["runpod_api_key"] == "key"
    assert result["runpod_endpoint_id"] == "endpoint"


def test_provider_concurrency_normalizes_stale_values_and_migrates_supported_legacy_setting():
    assert normalize_provider_concurrency(1) == 1
    assert normalize_provider_concurrency(2) == 2
    assert normalize_provider_concurrency(3) == 3
    assert normalize_provider_concurrency(5) == 3
    assert normalize_provider_concurrency(10) == 3
    assert normalize_provider_concurrency(None, legacy_value=2) == 2
    assert normalize_provider_concurrency(None, legacy_value=5) == 3


def test_runtime_settings_adds_normalized_provider_concurrency():
    assert build_runtime_settings({"generation_concurrency": 2}, {})["kie_concurrency"] == 2
    assert build_runtime_settings({"kie_concurrency": 4}, {})["kie_concurrency"] == 3
    assert build_runtime_settings({}, {})["photoroom_concurrency"] == 3
    assert build_runtime_settings({}, {})["fal_concurrency"] == 3
    assert build_runtime_settings({"fal_concurrency": 35}, {})["fal_concurrency"] == 3


def test_shared_api_concurrency_accepts_1_to_5_and_preserves_legacy_profiles():
    for value in range(1, 6):
        assert normalize_api_concurrency(value) == value
        assert build_runtime_settings({"api_concurrency": value, "kie_concurrency": 2}, {})["api_concurrency"] == value
    assert normalize_api_concurrency(9) == 3
    assert normalize_api_concurrency(None, legacy_value=2) == 2
    assert "api_concurrency" not in build_runtime_settings({"kie_concurrency": 2}, {})
