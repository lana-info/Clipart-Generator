"""Mockup: step list where every step is clickable and an unfilled step carries the existing red ✕ badge.

Rendered with the real V3StepLabel (v3_components), so badge, colours and row height are the approved ones.
Run: QT_QPA_PLATFORM=offscreen python docs/ui/3.2/step-navigation-20261026/render_proposed.py
"""
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))

from PyQt6.QtWidgets import QApplication, QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from v3_components import DEFAULT_TOKENS, V3StepLabel, apply_v3_theme

app = QApplication([])


def panel(title, rows, note):
    box = QFrame()
    box.setFixedWidth(300)
    layout = QVBoxLayout(box)
    head = QLabel(title)
    head.setStyleSheet("font-weight:700; color:#e4edf6;")
    layout.addWidget(head)
    for text in rows:
        layout.addWidget(V3StepLabel(text, DEFAULT_TOKENS))
    layout.addStretch(1)
    foot = QLabel(note)
    foot.setWordWrap(True)
    foot.setStyleSheet("color:#8ea3b8;")
    layout.addWidget(foot)
    return box


root = QWidget()
apply_v3_theme(root, DEFAULT_TOKENS)
row = QHBoxLayout(root)
row.addWidget(panel("Сейчас", ["✓ 1. Идеи", "● 2. Референсы", "○ 3. Настройки", "○ 4. Запуск"],
                    "Шаги не нажимаются. Вперёд — только «Далее», и только если шаг заполнен."))
row.addWidget(panel("Предлагается", ["✓ 1. Идеи", "✕ 2. Референсы", "● 3. Настройки", "○ 4. Запуск"],
                    "Любой шаг нажимается. ✕ — шаг не заполнен (красный крестик из шапки списка шагов). "
                    "«Далее» не блокируется, «Запустить» проверяет всё."))
root.resize(660, 330)
root.grab().save(str(Path(__file__).with_name("proposed.png")))
