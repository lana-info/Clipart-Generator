"""Real AppShell for the approved step-navigation mockup (proposed.png). Run from the repo root:
QT_QPA_PLATFORM=offscreen python docs/ui/3.2/step-navigation-20261026/capture_actual.py"""
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from PyQt6.QtWidgets import QApplication

from test_v3_wizard_navigation import complete_state
from v3_project_state import ProjectMode, StepId
from v3_wizard import AppShell

app = QApplication([])
state = complete_state(ProjectMode.CLIPART)
shell = AppShell(state)
shell.go_next()
state.clipart.prompts.clear()  # step 2 «Промпты» is now not filled in
shell.go_next()
shell.resize(1120, 780)
shell.show()
app.processEvents()
shell.grab().save(str(Path(__file__).with_name("actual.png")))
print([label.text() for label in shell.step_labels])
