from runtime_settings import build_runtime_settings, normalize_kie_concurrency


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


def test_kie_concurrency_normalizes_stale_values_and_migrates_legacy_setting():
    assert normalize_kie_concurrency(1) == 1
    assert normalize_kie_concurrency(10) == 10
    assert normalize_kie_concurrency(4) == 3
    assert normalize_kie_concurrency(None, legacy_value=5) == 5
    assert normalize_kie_concurrency(None, legacy_value=99) == 3


def test_runtime_settings_adds_normalized_global_kie_concurrency():
    assert build_runtime_settings({"generation_concurrency": 5}, {})["kie_concurrency"] == 5
    assert build_runtime_settings({"kie_concurrency": 4}, {})["kie_concurrency"] == 3
