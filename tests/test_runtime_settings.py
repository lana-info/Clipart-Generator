from runtime_settings import build_runtime_settings


def test_runtime_settings_snapshot_merges_secrets_without_mutating_config():
    config = {"timeout": 60, "kie_api_key": "legacy"}
    result = build_runtime_settings(config, {"kie_api_key": " fresh "})
    assert result["kie_api_key"] == "fresh"
    assert config["kie_api_key"] == "legacy"
