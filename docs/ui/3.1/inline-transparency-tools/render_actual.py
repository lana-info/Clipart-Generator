"""Render the implemented editor with synthetic artwork, never customer files."""
import os
import sys
import tempfile
from threading import Event
from unittest.mock import patch
from pathlib import Path
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
from PIL import Image, ImageDraw
from PyQt6.QtWidgets import QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel
from v3_components import apply_v3_theme
from v3_transparency_preview import ClipartTransparencyEditorPage
from studio_contour_smoke import check_contour_editing, _wait_for_contour

app = QApplication([])
out = Path(__file__).parent
with tempfile.TemporaryDirectory() as folder:
    source = Path(folder) / 'cup-01.png'
    im = Image.new('RGBA', (512,512))
    draw = ImageDraw.Draw(im)
    draw.ellipse((280,178,432,332), fill='#2a9d95')
    draw.ellipse((305,201,405,307), fill=(0,0,0,0))
    draw.rounded_rectangle((112,167,334,372), radius=38, fill='#3eafa4')
    draw.ellipse((112,135,334,201), fill='#98ded0')
    draw.ellipse((127,148,319,186), fill='#694338')
    draw.ellipse((187,231,257,301), fill='#ffe0a3')
    im.save(source)
    win = QWidget(); win.resize(1120,780); apply_v3_theme(win)
    layout = QVBoxLayout(win); layout.setContentsMargins(20,16,20,16)
    header = QHBoxLayout(); header.addWidget(QLabel('VIBIX  Studio')); header.addStretch()
    header.addWidget(QLabel('Обработка  /  Прозрачность')); layout.addLayout(header)
    page = ClipartTransparencyEditorPage(); layout.addWidget(page,1)
    page.set_files([source]); win.show(); app.processEvents()
    for state in ('brush', 'pen-empty', 'busy', 'pen', 'missing', 'error'):
        if state == 'pen-empty': page._set_tool('pen')
        if state == 'busy':
            release = Event()
            from v3_transparency_preview import _calculate_contour
            def delayed(*args):
                release.wait(5)
                return _calculate_contour(*args)
            with patch('v3_transparency_preview._calculate_contour', side_effect=delayed):
                page.contour_button.click()
                app.processEvents()
                win.grab().save(str(out / 'actual-busy-1120x780.png'))
                page.canvas.cancel_contour(); release.set(); _wait_for_contour(page.canvas)
            continue
        if state == 'pen':
            page.contour_button.click()
            _wait_for_contour(page.canvas)
            page.canvas.contour.selected = (0,0)
        if state == 'missing': page.set_files([])
        if state == 'error':
            Image.new('RGBA',(128,128),(20,60,90,255)).save(source)
            page.set_files([source]); page.contour_button.click(); _wait_for_contour(page.canvas)
        app.processEvents()
        assert (win.width(),win.height()) == (1120,780)
        win.grab().save(str(out / f'actual-{state}-1120x780.png'))
    win.close()
    assert check_contour_editing(out / 'smoke')
print('Actual UI states and integrated contour smoke passed')
