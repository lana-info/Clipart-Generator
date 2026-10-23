"""Capture integrated Qt states with the same safe dummy content as the approved mockup."""
import ast
from concurrent.futures import Future
import json
from pathlib import Path
import sys
import tempfile

import numpy as np
from PIL import Image, ImageDraw
from PyQt6.QtWidgets import QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel
from PyQt6.QtTest import QTest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
from v3_components import apply_v3_theme
from v3_transparency_preview import ClipartTransparencyEditorPage

OUT = Path(__file__).parent / 'actual'
OUT.mkdir(exist_ok=True)
app = QApplication.instance() or QApplication([])
# Load only the pure fixture function. Do not rerun or overwrite the approved proposal.
source_ast = ast.parse((Path(__file__).parent / 'render_proposal.py').read_text())
fixture_ast = next(node for node in source_ast.body if isinstance(node, ast.FunctionDef) and node.name == 'fixture')
exec(compile(ast.Module(body=[fixture_ast], type_ignores=[]), '<safe mockup fixture>', 'exec'))


def wait_result(page):
    for _ in range(200):
        app.processEvents()
        if page._colour_job is None:
            return
        QTest.qWait(5)
    raise AssertionError('worker did not finish')


records = []
with tempfile.TemporaryDirectory(prefix='vibix-colour-actual-') as temporary:
    filename = Path(temporary) / 'sample-01.png'
    fixture()[0].save(filename)
    for state in ['ready', 'selecting', 'busy', 'preview-before', 'preview-after', 'preview-dark', 'empty', 'no-op']:
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
        root.show()
        app.processEvents()
        page.canvas.set_zoom(None)
        if state not in ('ready', 'empty'):
            page.start_colour_correction()
            page.canvas.colour_selection_bounds = (125, 175, 192, 387)
        if state == 'busy':
            future = Future()
            with patch('v3_transparency_preview._CONTOUR_EXECUTOR.submit', return_value=future):
                page._start_colour_region((125, 175, 192, 387))
        elif state.startswith('preview'):
            page._start_colour_region((125, 175, 192, 387))
            wait_result(page)
            assert page._colour_preview is not None
            page.show_edge_preview(state != 'preview-before')
            page._set_background('Чёрный' if state == 'preview-dark' else 'Белый')
        elif state == 'no-op':
            page.canvas.colour_selection_bounds = (0, 0, 32, 32)
            page._start_colour_region((0, 0, 32, 32))
            wait_result(page)
            assert page._colour_preview is None
        app.processEvents()
        assert root.size().width() == 1120 and root.size().height() == 780
        # No scrolling is needed to reach the new action or the preview footer.
        viewport = page.tools_scroll.viewport().rect()
        controls = [page.colour_edge_button]
        if page._colour_active:
            controls.extend([page.cancel_edge_button, page.apply_edge_button, page.edge_note])
        for widget in controls:
            rect = widget.rect().translated(widget.mapTo(page.tools_scroll.viewport(), widget.rect().topLeft()))
            assert viewport.contains(rect), (state, widget.text(), rect, viewport)
        root.grab().save(str(OUT / f'{state}.png'))
        record = {'state': state, 'size': [1120, 780], 'controls_reachable_without_scroll': True,
                  'source_unchanged': not page._document or not page.document.is_dirty}
        records.append(record)
        root.close()
        root.deleteLater()
        app.processEvents()
(OUT / 'verification.json').write_text(json.dumps({'safe_synthetic_content_only': True,
    'production_ui': True, 'environment': 'Linux Qt offscreen, 100% scale', 'states': records,
    'busy_note': 'Real integrated job state captured with a held Future; other effect previews ran production RGB worker.',
    'approved_reference': '../proposal/notes.json'}, ensure_ascii=False, indent=2) + '\n')
print(json.dumps(records))
