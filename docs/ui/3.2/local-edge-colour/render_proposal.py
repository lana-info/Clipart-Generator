"""UI approval mockups only; production controls are not changed here."""
from pathlib import Path
import json
import sys
import tempfile

import numpy as np
from PIL import Image, ImageDraw
from PyQt6.QtCore import Qt, QRectF
from PyQt6.QtGui import QColor, QPen
from PyQt6.QtWidgets import QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
from v3_components import apply_v3_theme
from v3_transparency_preview import ClipartTransparencyEditorPage, _pixmap_for_pil

OUT = Path(__file__).parent / 'proposal'
OUT.mkdir(exist_ok=True)
if (OUT / 'notes.json').exists():
    saved = json.loads((OUT / 'notes.json').read_text())
    if saved.get('approval') != 'pending':
        raise SystemExit('Approved mockup is preserved. Capture integrated states with render_actual.py.')
app = QApplication.instance() or QApplication([])


def fixture():
    image = Image.new('RGBA', (620, 500))
    draw = ImageDraw.Draw(image)
    draw.ellipse((394, 155, 538, 345), fill=(51, 148, 144, 255))
    draw.ellipse((420, 183, 510, 320), fill=(0, 0, 0, 0))
    draw.rounded_rectangle((148, 138, 414, 421), radius=36, fill=(65, 171, 163, 255))
    draw.ellipse((148, 114, 414, 174), fill=(155, 222, 209, 255))
    draw.ellipse((163, 126, 399, 161), fill=(101, 65, 54, 255))
    draw.ellipse((238, 235, 324, 321), fill=(255, 224, 161, 255))
    correct = np.array(image)
    before = correct.copy()
    # Known dummy fringe; this is a layout illustration, not actual-image QA.
    before[180:382, 148:152, :3] = (130, 112, 167)
    before[180:382, 147, :] = (130, 112, 167, 128)
    correct[180:382, 147, :] = (65, 171, 163, 128)
    return Image.fromarray(before), Image.fromarray(correct)


def render(state, source, clean, filename):
    root = QWidget()
    root.resize(1120, 780)
    apply_v3_theme(root)
    layout = QVBoxLayout(root)
    layout.setContentsMargins(20, 14, 20, 16)
    layout.setSpacing(8)
    header = QHBoxLayout()
    header.addWidget(QLabel('VIBIX  Studio'))
    header.addStretch()
    header.addWidget(QLabel('Обработка  /  Прозрачность'))
    layout.addLayout(header)
    page = ClipartTransparencyEditorPage()
    layout.addWidget(page, 1)
    if state != 'empty':
        page.set_files([filename], save_dir=filename.parent / 'edited')
    if state != 'current':
        page.files_frame.setMaximumHeight(238)
        button = QPushButton('Убрать цветную кайму')
        button.setCheckable(True)
        controls = page.sharpen_edge_button.parentWidget().layout()
        index = controls.indexOf(page.sharpen_edge_button) + 1
        controls.insertWidget(index, button)
        note = QLabel()
        note.setWordWrap(True)
        note.setStyleSheet('font-size:11px;color:#b7c6d7;')
        controls.insertWidget(index + 1, note)
        note.hide()
        button.setEnabled(state != 'empty')
        active = state in ('selecting', 'preview-before', 'preview-after', 'preview-dark', 'busy', 'no-op')
        if active:
            button.setChecked(True)
            page.sharpen_edge_button.setEnabled(False)
            for item in (*page.tool_buttons.values(), page.undo_button, page.redo_button,
                         page.reset_button, page.save_button):
                item.setEnabled(False)
            page.brush_controls.hide()
            page.pen_controls.hide()
            page.edge_comparison.show()
            page.edge_comparison.findChild(QLabel).setText('Цвет меняется, форма края сохраняется')
            page.edge_before_button.setEnabled(state.startswith('preview'))
            page.edge_after_button.setEnabled(state.startswith('preview'))
            page.apply_edge_button.setEnabled(state.startswith('preview'))
            note.show()
            note.setText('Обведите проблемный край рамкой.' if state == 'selecting'
                         else 'Проверьте выбранный край на белом и тёмном фоне.')
            if state == 'no-op':
                note.setText('В этом участке нет подходящей опоры цвета. Выделите другой участок.')
            elif state == 'busy':
                note.setText('Корректирую выбранный край… Можно отменить.')
        if state.startswith('preview'):
            after = state in ('preview-after', 'preview-dark')
            page.edge_before_button.setChecked(not after)
            page.edge_after_button.setChecked(after)
            page.canvas._item.setPixmap(_pixmap_for_pil(clean if after else source))
        if active:
            pen = QPen(QColor('#28cbbb'), 1.5, Qt.PenStyle.DashLine)
            pen.setCosmetic(True)
            page.canvas._scene.addRect(QRectF(125, 175, 67, 212), pen)
    if state in ('preview-after', 'preview-before'):
        page._set_background('Белый')
    elif state == 'preview-dark':
        page._set_background('Чёрный')
    root.show()
    app.processEvents()
    page.canvas.set_zoom(None)
    if state in ('preview-after', 'preview-dark'):
        page.canvas._item.setPixmap(_pixmap_for_pil(clean))
    app.processEvents()
    root.grab().save(str(OUT / f'{state}.png'))
    root.close()
    root.deleteLater()
    app.processEvents()


source, clean = fixture()
states = ['current', 'ready', 'selecting', 'busy', 'preview-before', 'preview-after', 'preview-dark', 'empty', 'no-op']
with tempfile.TemporaryDirectory(prefix='vibix-colour-mockup-') as temporary:
    filename = Path(temporary) / 'sample-01.png'
    source.save(filename)
    for state in states:
        render(state, source, clean, filename)
(OUT / 'notes.json').write_text(json.dumps({
    'approval': 'pending', 'target': '1120x780, 100% scaling, Qt offscreen',
    'states': states, 'safe_synthetic_content_only': True,
    'production_ui_changed': False,
    'interaction': 'Click correction, draw rectangle over edge, preview Before/After, Cancel or Apply. '
                   'White/dark/checker background and zoom stay available. '
                   'RGB changes only in selected edge; alpha/shape/source unchanged. '
                   'No strength slider. No-op leaves image/history untouched.',
}, ensure_ascii=False, indent=2))
