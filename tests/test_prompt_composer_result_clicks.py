"""Real Qt event delivery, isolated so native crashes cannot kill pytest."""
import os
from pathlib import Path
import subprocess
import sys
import textwrap

import pytest


@pytest.mark.parametrize('scene', ['minimal', 'filled', 'ai-proposal', 'signed-module'])
def test_result_mouse_and_keyboard_selection_keeps_qt_alive(scene, tmp_path):
    code = textwrap.dedent('''
        import faulthandler
        import sys
        from copy import deepcopy
        from unittest.mock import patch
        from PyQt6.QtCore import Qt, QCoreApplication, QEvent
        from PyQt6 import sip
        from PyQt6.QtTest import QTest
        from PyQt6.QtWidgets import QApplication, QListWidget, QPushButton, QTextEdit
        from prompt_composer.ui import PromptComposerPage
        from studio_prompt_composer_host import PromptComposerHost

        faulthandler.enable()
        app = QApplication([])
        errors = []
        sys.excepthook = lambda kind, error, tb: errors.append(str(error))
        scene = sys.argv[2]
        if scene == 'signed-module':
            from pathlib import Path
            from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
            from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
            from studio_module_packaging import prepare_module_release
            from studio_module_runtime import ModuleRuntimeHost
            from studio_modules import ModuleStore
            from studio_prompt_composer_package import composer_payload
            key = Ed25519PrivateKey.generate()  # Temporary test signer only.
            package = prepare_module_release(module_id='prompt-composer', version='1.0.0',
                studio_min='3.2.12', studio_max_exclusive='3.3.0', platforms=['linux-x64'],
                entrypoint='entry.py', files=composer_payload(Path.cwd()), key_id='test', private_key=key)
            package_path = Path(sys.argv[1]).parent / 'test-composer.zip'
            package_path.write_bytes(package)
            store = ModuleStore(Path(sys.argv[1]).parent / 'modules', studio_version='3.2.12',
                platform='linux-x64', trusted_keys={'test': key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)})
            store.install(package_path)
            store.activate('prompt-composer', '1.0.0')
            runtime = ModuleRuntimeHost(store, lambda module, action: True)
            runtime.load_active('prompt-composer')
            kernel = runtime.invoke_command('prompt-composer', 'kernel')
            host = PromptComposerHost(sys.argv[1], settings_provider=lambda: {}, authorize=lambda: True,
                                      runtime=runtime, kernel=kernel)
            handle = runtime.create_page('prompt-composer', 'main', host)
            page = handle.value
            assert page.__class__.__module__.startswith('_studio_module_prompt_composer_')
        else:
            host = PromptComposerHost(sys.argv[1], settings_provider=lambda: {}, authorize=lambda: True)
            page = PromptComposerPage(host)
        page.resize(1120, 780)
        page.show()
        scene = sys.argv[2]
        if scene == 'filled':
            page.draft['fields'].update(location={'ru': 'студия', 'en': 'studio'},
                                        color={'ru': 'синий', 'en': 'blue'})
        assert page.generate_local()
        if scene == 'ai-proposal':
            # Already received suggestions; no provider or paid operation.
            page._proposal = {'variants': deepcopy(page._variants), 'status': 'complete', 'stale': False}
            page._proposal_index = 0
            page._render()
        app.processEvents()
        for row in list(range(1, 7)) + list(range(5, -1, -1)):
            listing = page.findChild(QListWidget, 'variantList')
            assert listing.count() == 7
            QTest.mouseClick(listing.viewport(), Qt.MouseButton.LeftButton,
                             pos=listing.visualItemRect(listing.item(row)).center())
            app.processEvents()
            QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
            assert sip.isdeleted(listing)
            assert (page._proposal_index if page._proposal else page._variant_index) == row
            assert page.findChild(QTextEdit, 'promptText').toPlainText() == page._variant_text(page._active_variant(), 'en')
        page.findChild(QListWidget, 'variantList').setFocus()
        for key, expected_row in ((Qt.Key.Key_Down, 1), (Qt.Key.Key_Down, 2),
                                  (Qt.Key.Key_Up, 1), (Qt.Key.Key_End, 6), (Qt.Key.Key_Home, 0)):
            assert app.focusWidget().objectName() == 'variantList'
            QTest.keyClick(app.focusWidget(), key)
            app.processEvents()
            assert (page._proposal_index if page._proposal else page._variant_index) == expected_row
            assert page._active_variant()
        for button in ('languageRuButton', 'languageEnButton', 'copyEnButton'):
            page.findChild(QPushButton, button).click()
            app.processEvents()
        assert app.clipboard().text() == page._variant_text(page._active_variant(), 'en')
        if scene != 'ai-proposal':
            with patch('PyQt6.QtWidgets.QDialog.exec', return_value=1):
                assert page.save_current()
            saved = host.load(page._saved_record['id'])
            assert saved['payload']['base_en'] == page._active_variant()['en']
            page.findChild(QPushButton, 'moreVariantsButton').click()
            app.processEvents()
            assert len(page._variants) == 7
        assert not errors, errors
        host.close()
        page.close()
        if scene == 'signed-module':
            handle.close()
        print('PASS: real mouse/key events, text/copy/save/more')
    ''')
    root = Path(__file__).resolve().parents[1]
    environment = dict(os.environ, QT_QPA_PLATFORM='offscreen', PYTHONDONTWRITEBYTECODE='1')
    environment['PYTHONPATH'] = str(root)
    result = subprocess.run([sys.executable, '-B', '-c', code, str(tmp_path / 'library'), scene],
                            cwd=root, env=environment, capture_output=True, text=True, timeout=40)
    assert result.returncode == 0, f'Qt child exit {result.returncode}:\n{result.stdout}\n{result.stderr}'
    assert 'PASS: real mouse/key events' in result.stdout
