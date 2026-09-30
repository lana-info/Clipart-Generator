"""Local reference import through the approved Composer page."""
from unittest.mock import patch

import pytest
from PyQt6.QtWidgets import QApplication


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def test_real_reference_import_through_ui(tmp_path, app):
    from PIL import Image
    from prompt_composer.ui import PromptComposerPage
    from studio_prompt_composer_host import PromptComposerHost
    image = tmp_path / 'sample.png'
    Image.new('RGB', (20, 20), 'blue').save(image)
    host = PromptComposerHost(tmp_path / 'library', settings_provider=lambda: {}, authorize=lambda: True)
    page = PromptComposerPage(host)
    with patch('prompt_composer.ui.QFileDialog.getOpenFileName', return_value=(str(image), '')):
        assert page.import_reference()
    saved = host.save(page.draft, {'name': 'С референсом'})
    image.unlink()
    assert host.reference_available(saved['payload']['references'][0])
    assert saved['payload']['references'][0]['filename'] == 'sample.png'
    page._dirty = False
    page.confirm_close()
    page.deleteLater()
