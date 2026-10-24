"""REAL screen capture of step 2 after the UI change (no patches).
Run: python render_proposed.py <repo> <out_dir>"""
import os, sys
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
repo, out = sys.argv[1], sys.argv[2]
sys.path.insert(0, repo)
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import QApplication, QHBoxLayout, QLabel, QPushButton, QScrollArea, QVBoxLayout
app = QApplication.instance() or QApplication([])
from license_client import LicenseAuthorization, ModuleEntitlement
from v3_mode_selection import V3ApplicationView
from v3_components import DEFAULT_TOKENS as T
import studio_clipart_builder_ui as B

now = datetime.now(timezone.utc)
auth = LicenseAuthorization("fixture","clipart-generator","fixture",now,now+timedelta(minutes=5),
    module_entitlements=(ModuleEntitlement("auto-clipart",now,now+timedelta(minutes=5)),))
class Gate:
    status_text = verification_text = "Offline fixture"; current_authorization = auth
    def authorize_run(self): return auth
def no_worker(**k): raise AssertionError("no generation")
with TemporaryDirectory() as t:
    root = Path(t)
    v = V3ApplicationView(draft_path=root/"draft.json", license_gate=Gate(), worker_factory=no_worker, runtime_settings_provider=lambda: {})
    v.resize(1120, 780); v.show()
    v._handle_module_action("auto-clipart", "open")
    c = v.shell.workflow_controller("auto-clipart")
    c.brief.directory.setText(str(root)); c.brief.theme.setText("Winter flowers"); c.brief.total.setValue(3)
    v.shell.go_next(); app.processEvents()
    b = c.brief
    app.processEvents()
    def shot(n): app.processEvents(); v.grab().save(f"{out}/{n}.png")
    shot("step-2-tabs-default")
    b._select_style_profile(b.style_cards[1]["key"])
    keys = list(b.style_modifier_buttons)
    for k in keys[:2]: b.style_modifier_buttons[k].setChecked(True)
    shot("step-2-tabs-style")
    b.palette_cards[0]["button"].click(); b.style_tabs.setCurrentIndex(1); shot("step-2-tabs-palette")
    b.style_tabs.setCurrentIndex(2); shot("step-2-tabs-fine")
    c.save_timer.stop(); v.close()
print("done")
