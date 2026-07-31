from runtime_settings import build_runtime_settings


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
