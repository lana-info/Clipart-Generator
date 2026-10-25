import os, sys
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
repo, out = sys.argv[1], sys.argv[2]
sys.path.insert(0, repo)
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from PyQt6.QtWidgets import QApplication
app = QApplication.instance() or QApplication([])
from license_client import LicenseAuthorization, ModuleEntitlement
from v3_mode_selection import V3ApplicationView
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
    def snap(n): app.processEvents(); v.grab().save(f"{out}/{n}.png")
    snap("step-1")
    for i in range(2, 6):
        v.shell.go_next(); snap(f"step-{i}")
    for it in c.brief.object_editor.items: it["name"] = f"Winter flower {it['ordinal']}"
    c.brief.object_editor.refresh()
    v.shell.go_next(); snap("step-6")
    c.save_timer.stop(); v.close()
print("done")
