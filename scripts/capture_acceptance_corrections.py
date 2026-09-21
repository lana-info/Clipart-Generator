"""Capture offline acceptance views with synthetic project data and no API calls."""
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock
from PIL import Image

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PyQt6.QtWidgets import QApplication
from license_client import LicenseAuthorization, ModuleEntitlement
from v3_mode_selection import V3ApplicationView
from v3_project_state import StepId


def main():
    output = Path(sys.argv[1])
    output.mkdir(parents=True, exist_ok=True)
    app = QApplication.instance() or QApplication([])
    now = datetime.now(timezone.utc)
    gate = Mock(status_text='Лицензия активна', verification_text='Тестовые данные')
    gate.current_authorization = LicenseAuthorization('fixture', 'clipart-generator', 'fixture',
        now, now + timedelta(hours=1), module_entitlements=(
            ModuleEntitlement('auto-clipart', now, now + timedelta(hours=1)),))
    gate.authorize_run.return_value = gate.current_authorization
    with TemporaryDirectory() as directory:
        view = V3ApplicationView(license_gate=gate, draft_path=Path(directory) / 'draft.json')
        view.resize(1120, 780)
        view.show()
        view._handle_module_action('auto-clipart', 'open')
        controller = view.shell.workflow_controller('auto-clipart')
        controller.save_timer.stop()
        controller.brief.directory.setText(directory)
        controller.brief.theme.setText('Зимние цветы')
        for label, step in [('idea', StepId.PROJECT), ('style', StepId.PROMPTS),
                            ('references', StepId.PROMPT_REVIEW), ('objects', StepId.PROCESSING_OPTIONS)]:
            controller._select_step(step)
            app.processEvents()
            view.grab().save(str(output / f'{label}-1120x780.png'))
        controller._select_step(StepId.PROMPTS)
        brief = controller.brief
        brief.palette_cards[3]['button'].click()
        brief.pages.currentWidget().ensureWidgetVisible(brief.palette_cards[3]['widget'])
        app.processEvents()
        view.grab().save(str(output / 'palette-selected-1120x780.png'))
        reference = Path(directory) / 'reference.png'
        Image.new('RGB', (128, 128), '#20c9b7').save(reference)
        brief.reference_editor.add_reference(str(reference))
        controller._select_step(StepId.PROMPT_REVIEW)
        app.processEvents()
        view.grab().save(str(output / 'references-populated-1120x780.png'))
        view.show_mode_switcher()
        app.processEvents()
        view.grab().save(str(output / 'home-1120x780.png'))
        view.close()


if __name__ == '__main__':
    main()
