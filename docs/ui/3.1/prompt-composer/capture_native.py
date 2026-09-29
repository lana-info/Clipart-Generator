"""Capture the real Qt shell with temporary data and a synthetic test entitlement.
No credentials are read and no network operation is launched.
"""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[4]))
from copy import deepcopy
import json
import tempfile
from unittest.mock import patch
from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QApplication, QDialog, QMessageBox
from v3_mode_selection import V3ApplicationView
from tests.test_prompt_composer_integration import Gate

out = Path(__file__).parent / 'native'
out.mkdir(exist_ok=True)
app = QApplication.instance() or QApplication([])
checks = []
with tempfile.TemporaryDirectory() as temp:
    view = V3ApplicationView(draft_path=Path(temp) / 'draft.json', license_gate=Gate())
    view.resize(1120, 780)
    view.show()
    view._open_composer('prompt-composer', 'open')
    page = view._composer_page_handle.value
    def shot(name, widget=view):
        app.processEvents()
        widget.grab().save(str(out / f'{name}.png'))
        checks.append({'state': name, 'width': widget.width(), 'height': widget.height(),
                       'horizontal_scroll': page.scroll.horizontalScrollBar().maximum() if widget is view else None})
    shot('templates')
    templates = page.host.catalogue()['templates']
    template = next(t for t in templates if t['draft']['mode'] == 'image' and t['draft']['subject_type'] == 'product')
    page.apply_template(template)
    shot('subject-product')
    page.goto_step(2)
    shot('details')
    page.goto_step(3)
    shot('scene-image')
    page.generate_local()
    shot('results-en')
    page._change_language('ru')
    shot('results-ru')
    page._variant_edits[0] = {'manual_en': 'A matte ceramic mug beside a window, soft daylight.', 'translation_stale': True}
    page._change_language('en')
    shot('manual')
    for i in range(4):
        value = page._variants[i]['draft']
        page.host.save(value, {'name': ['Керамика у окна', 'Мягкий свет', 'Предметный кадр', 'Каталог товара'][i], 'tags': ['товар'], 'favorite': i == 0})
    page._dirty = False
    page._show_tab('library')
    shot('library')
    page.new_draft()
    page.apply_template(next(t for t in templates if t['draft']['mode'] == 'reels'))
    page.goto_step(3)
    shot('scene-reels')
    page.generate_local()
    shot('results-reels')
    local = page.host.generate(page.host.new_draft())
    page._proposal = {'variants': deepcopy(local['variants'][:3]), 'status': 'insufficient',
                      'reason': 'Доступно три предложения; автоматического добора нет.', 'snapshot': deepcopy(page.draft), 'stale': False}
    for variant in page._proposal['variants']:
        variant['source'] = 'ai'
        variant['warnings'] = ['Проверьте смысл и соответствие RU/EN перед использованием.']
    page._render()
    shot('ai-partial-fixture')
    page._proposal['stale'] = True
    page._render()
    shot('ai-stale-fixture')
    def dialog_capture(name):
        def capture():
            dialog = app.activeModalWidget()
            if dialog:
                shot(name, dialog)
                dialog.reject()
        QTimer.singleShot(50, capture)
    dialog_capture('ai-price-fixture')
    page._quote_consent({'provider': 'openrouter', 'model': 'Демонстрационная модель', 'price': .01}, 'Семь вариантов')
    dialog_capture('ai-unknown-price')
    page._quote_consent({'provider': 'openrouter', 'model': 'Демонстрационная модель', 'price': None}, 'Семь вариантов')
    page._proposal = None
    dialog_capture('save-dialog')
    page.save_current()
    dialog_capture('reference-error')
    page._show_message('Файл референса недоступен. Сохранённый промпт можно использовать без него.')
    page._dirty = False
    page.confirm_close()
    view.close()
(out / 'checks.json').write_text(json.dumps(checks, ensure_ascii=False, indent=2))
print(f'{len(checks)} native screens captured; horizontal overflow:', [c['state'] for c in checks if c['horizontal_scroll']])
