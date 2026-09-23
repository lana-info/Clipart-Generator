"""Seed synthetic 3.1.4 user files and check their preservation on a CI runner.

Never run --seed on a customer profile: it refuses to replace existing files.
The manifest records hashes and paths only, never credential contents.
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PyQt6.QtCore import QStandardPaths
from PyQt6.QtWidgets import QApplication


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', choices=['seed', 'verify'])
    parser.add_argument('manifest', type=Path)
    args = parser.parse_args()
    app = QApplication.instance() or QApplication([])
    # This is the shipped 3.1.4 Qt identity, not the new display label.
    app.setOrganizationName('Vibix')
    app.setApplicationName('Vibix Images')
    legacy_qt = Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppDataLocation))
    import main as client
    legacy_user = Path(client.USER_DATA_DIR)
    assert legacy_user.name == 'Vibix Images'
    if args.operation == 'seed':
        files = {
            legacy_user / 'config.json': b'{"migration_fixture":"3.1.4","threads":2}',
            legacy_user / 'prompts.json': b'["Preserve old prompt"]',
            legacy_user / 'fal_api_key.bin': b'non-secret-upgrade-sentinel',
            legacy_qt / 'license_state.json': b'{"upgrade_fixture":"retain-device-state"}',
            legacy_qt / 'projects' / 'upgrade-sentinel.json': b'{"upgrade_fixture":"retain-project"}',
        }
        assert not args.manifest.exists()
        assert not any(path.exists() for path in files), 'Refusing to replace existing user files'
        for path, content in files.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open('xb') as stream:
                stream.write(content)
        payload = dict(qt_root=str(legacy_qt), user_root=str(legacy_user),
                       files={str(p): hashlib.sha256(content).hexdigest() for p, content in files.items()})
        args.manifest.write_text(json.dumps(payload, indent=2))
    else:
        payload = json.loads(args.manifest.read_text())
        client.configure_application_identity(app)
        assert app.applicationDisplayName() == 'Vibix Studio'
        assert Path(client.USER_DATA_DIR) == Path(payload['user_root'])
        assert Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppDataLocation)) == Path(payload['qt_root'])
        for path, expected in payload['files'].items():
            assert hashlib.sha256(Path(path).read_bytes()).hexdigest() == expected, 'Old user file changed'
        print('PASS: Studio preserves 3.1.4 Qt/local storage paths and all five synthetic user files')


if __name__ == '__main__':
    main()
