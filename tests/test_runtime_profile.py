import base64
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from runtime_profile import PRODUCTION_LICENSE_KEYS, validate_acceptance_profile
from release_contract import ReleaseContractError, validate_release_contract

ROOT = Path(__file__).resolve().parents[1]


def test_acceptance_installer_never_passes_production_contract():
    validate_release_contract("3.2.0", installer_name="VibixImages-Test-Setup-3.2.0.exe", acceptance=True)
    with pytest.raises(ReleaseContractError):
        validate_release_contract("3.2.0", installer_name="VibixImages-Test-Setup-3.2.0.exe")
    with pytest.raises(ReleaseContractError):
        validate_release_contract("3.2.0", installer_name="VibixImages-Setup-3.2.0.exe", acceptance=True)


def test_acceptance_profile_is_public_only_and_not_production_trust():
    profile = json.loads((ROOT / "release/acceptance-profile.json").read_text())
    assert validate_acceptance_profile(profile) == profile
    assert set(profile) == {"kind", "service_url", "license_keys", "publisher_keys"}
    for overrides in (
        {"service_url": "https://services.etsyneuroclub.com/licenses"},
        {"service_url": "http://localhost/studio-test"},
        {"service_url": "https://user:password@example.com/studio-test"},
        {"license_keys": {}},
        {"private_key": "never accepted"},
        {"license_keys": {"license-v1": base64.b64encode(base64.urlsafe_b64decode(
            PRODUCTION_LICENSE_KEYS["license-v1"] + "=")).decode()}},
    ):
        with pytest.raises(ValueError):
            validate_acceptance_profile({**profile, **overrides})


def test_production_ignores_runtime_environment_overrides():
    result = subprocess.run([sys.executable, "-c", "import runtime_profile as p; assert not p.IS_ACCEPTANCE; "
                             "assert p.APP_NAME == 'Vibix Studio'; assert p.APP_STORAGE_NAME == 'Vibix Images'; assert p.MODULE_PUBLISHER_KEYS is None; "
                             "assert p.LICENSE_SERVICE_BASE_URL == p.PRODUCTION_SERVICE"],
        cwd=ROOT, env={**os.environ, "VIBIX_ACCEPTANCE": "1", "LICENSE_SERVICE_BASE_URL": "https://evil.invalid"},
        capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_compiled_profile_isolates_identity_storage_and_license_trust(tmp_path):
    profile = json.loads((ROOT / "release/acceptance-profile.json").read_text())
    (tmp_path / "_acceptance_build.py").write_text("PROFILE = " + repr(profile))
    code = """
import sys
sys.path.insert(0, sys.argv[1])
import runtime_profile as p
import main
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QStandardPaths
assert p.IS_ACCEPTANCE
assert p.APP_NAME == 'Vibix Studio Test'
assert main.LICENSE_SERVICE_BASE_URL.endswith('/studio-test')
assert main.LICENSE_PUBLIC_KEYS != p.PRODUCTION_LICENSE_KEYS
assert main.USER_DATA_DIR.endswith('Vibix Studio Test')
assert set(p.MODULE_PUBLISHER_KEYS) == {'acceptance-publisher-v1'}
app = QApplication([])
main.configure_application_identity(app)
assert QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppDataLocation).endswith('Vibix Studio Test')
"""
    result = subprocess.run([sys.executable, "-c", code, str(tmp_path)], cwd=ROOT,
        env={**os.environ, "LOCALAPPDATA": str(tmp_path), "HOME": str(tmp_path), "QT_QPA_PLATFORM": "offscreen"},
        capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
