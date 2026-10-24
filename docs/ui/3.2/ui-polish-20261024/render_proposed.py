"""Mockup render: real Studio screens with PROPOSED styling applied from this script only (product code untouched).
Run: python render_proposed.py <repo> <out_dir>"""
import os, sys, re
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
repo, out = sys.argv[1], sys.argv[2]
sys.path.insert(0, repo)
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from PyQt6.QtWidgets import QApplication, QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget
from PyQt6.QtCore import Qt
app = QApplication.instance() or QApplication([])
from license_client import LicenseAuthorization, ModuleEntitlement
from v3_mode_selection import V3ApplicationView
from v3_wizard import STEP_TITLES
from v3_components import V3Button, DEFAULT_TOKENS as T

QSS = f"""
QTabWidget::pane {{ border:1px solid {T.border}; border-radius:8px; top:-1px; background:{T.surface}; }}
QTabBar {{ background:transparent; }}
QTabBar::tab {{ background:transparent; color:{T.text_muted}; padding:9px 18px; border:none;
  border-bottom:2px solid transparent; font-weight:600; margin-right:2px; }}
QTabBar::tab:selected {{ color:{T.text}; border-bottom:2px solid {T.accent}; }}
QTabBar::tab:hover:!selected {{ color:{T.text}; background:{T.surface_muted}; }}
QAbstractScrollArea::corner {{ background:transparent; }}
"""

TITLES = []
def stepper(view, error_index=None):
    sh = view.shell
    lay = sh.steps_layout
    global TITLES
    if not TITLES:
        TITLES = [re.sub(r"^[✓●○✕]\s*\d+\.\s*", "", l.text()) for l in sh.step_labels if isinstance(l, QLabel)]
    titles = TITLES
    while lay.count():
        it = lay.takeAt(0)
        if it.widget(): it.widget().hide(); it.widget().deleteLater()
    cur = sh.state.route.index(sh.state.current_step)
    for i, step in enumerate(sh.state.route):
        row = QFrame(); rl = QHBoxLayout(row); rl.setContentsMargins(10, 8, 10, 8); rl.setSpacing(10)
        if i == error_index: kind = "error"
        elif i < cur: kind = "done"
        elif i == cur: kind = "current"
        else: kind = "todo"
        m = QLabel("✓" if kind == "done" else ("✕" if kind == "error" else str(i + 1)))
        m.setFixedSize(22, 22); m.setAlignment(Qt.AlignmentFlag.AlignCenter)
        mst = {"done": f"background:{T.accent_soft};color:{T.accent};border:1px solid {T.accent};",
               "current": f"background:{T.accent};color:#06201c;border:1px solid {T.accent};",
               "todo": f"background:transparent;color:{T.text_muted};border:1px solid {T.border};",
               "error": f"background:{T.error_soft};color:{T.error};border:1px solid {T.error};"}[kind]
        m.setStyleSheet(mst + "border-radius:11px;font-weight:700;font-size:12px;")
        t = QLabel(titles[i]); t.setWordWrap(True)
        tst = {"done": f"color:{T.text};font-weight:500;", "current": f"color:#ffffff;font-weight:700;",
               "todo": f"color:{T.text_muted};font-weight:400;", "error": f"color:{T.error};font-weight:600;"}[kind]
        t.setStyleSheet(tst + "background:transparent;border:none;")
        rl.addWidget(m, 0, Qt.AlignmentFlag.AlignTop); rl.addWidget(t, 1)
        row.setStyleSheet(
            (f"QFrame{{background:{T.surface_muted};border-left:3px solid {T.accent};border-radius:6px;}}" if kind == "current"
             else "QFrame{background:transparent;border:none;}"))
        lay.addWidget(row); row.show()
    lay.addStretch()

def toolbar(view):
    csv = next(b for b in view.findChildren(V3Button) if b.text().strip() == "CSV")
    host = csv.parentWidget(); hl = host.layout()
    hl.setContentsMargins(0, 6, 0, 6); hl.setSpacing(6)
    from PyQt6.QtWidgets import QTableWidget
    tb = next(w for w in view.findChildren(QTableWidget) if w.isVisible())
    tb.verticalHeader().setDefaultSectionSize(60)
    tb.setShowGrid(False)
    tb.setStyleSheet(f"QTableView::item{{padding:6px 12px;border-bottom:1px solid {T.border};}}"
                     f"QTableView::item:selected{{background:{T.accent_soft};color:{T.text};}}")
    for r in range(tb.rowCount()): tb.setRowHeight(r, 60)
    pl = host.parentWidget().layout()
    pl.removeWidget(host); pl.insertWidget(pl.indexOf(tb), host)
    hl.setContentsMargins(0, 4, 0, 10)
    # group separators before «Референсы:» and «Экспорт:»
    for lab in ("Референсы:", "Экспорт:"):
        pass
    for lab in ("Референсы:", "Экспорт:"):
        w = next(l for l in host.findChildren(QLabel) if l.text() == lab)
        idx = hl.indexOf(w)
        sep = QFrame(); sep.setFixedWidth(1); sep.setFixedHeight(28); sep.setStyleSheet(f"background:{T.border};")
        hl.insertWidget(idx, sep)
    for l in host.findChildren(QLabel):
        l.setStyleSheet(f"color:{T.text_muted};background:transparent;"); l.setText(l.text().rstrip(":")); l.adjustSize(); hl.setAlignment(l, Qt.AlignmentFlag.AlignVCenter)
    csv.setStyleSheet(f"QPushButton{{background:{T.surface_muted};color:{T.text};border:1px solid {T.border};"
                      f"border-radius:8px;font-weight:600;padding:0 14px;}}QPushButton:hover{{border-color:{T.accent};}}")
    csv.setText("Экспорт CSV"); csv.setFixedSize(144, 38)
    from PyQt6.QtCore import QSize
    for b in host.findChildren(V3Button):
        if b is not csv and b.text() == "":
            b.setFixedSize(42, 38); b.setIconSize(QSize(24, 24))
    hl.removeWidget(next(l for l in host.findChildren(QLabel) if l.text() == "Экспорт"))
    next(l for l in host.findChildren(QLabel) if l.text() == "Экспорт").hide()

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
    app.processEvents()
    TITLES[:] = [re.sub(r"^[✓●○✕]\s*\d+\.\s*", "", l.text()) for l in v.shell.step_labels if isinstance(l, QLabel)]
    print("TITLES", TITLES, [type(l).__name__ for l in v.shell.step_labels]); v.setStyleSheet(v.styleSheet() + QSS)
    def snap(n):
        app.processEvents(); v.grab().save(f"{out}/{n}.png")
    def settle(**kw):
        app.processEvents(); stepper(v, **kw); app.processEvents()
    v.shell.go_next(); app.processEvents(); titles_src = None; stepper(v); v.grab().save(f"{out}/step-2-proposed.png")
    for _ in range(3): v.shell.go_next()
    for it in c.brief.object_editor.items: it["name"] = f"Winter flower {it['ordinal']}"
    c.brief.object_editor.refresh()
    v.shell.go_next(); app.processEvents(); toolbar(v); stepper(v); app.processEvents(); app.processEvents(); v.grab().save(f"{out}/step-6-proposed.png")
    stepper(v, error_index=3); app.processEvents(); v.grab().save(f"{out}/step-6-proposed-error-state.png")
    c.save_timer.stop(); v.close()

# side-by-side composites
from PIL import Image, ImageDraw, ImageFont
import glob
_f = (glob.glob('/usr/share/fonts/**/DejaVuSans.ttf', recursive=True) or [None])[0]
font = ImageFont.truetype(_f, 18) if _f else None
for n in ("step-2", "step-6"):
    a = Image.open(f"{out}/../actual/{n}.png").convert("RGB"); b = Image.open(f"{out}/{n}-proposed.png").convert("RGB")
    W = a.width + b.width + 60; im = Image.new("RGB", (W, a.height + 50), (16, 24, 39)); d = ImageDraw.Draw(im)
    d.text((20, 10), "СЕЙЧАС (3.2.41)", fill=(146, 162, 179), font=font); d.text((a.width + 40, 10), "ПРЕДЛАГАЕТСЯ", fill=(45, 212, 191), font=font)
    im.paste(a, (20, 40)); im.paste(b, (a.width + 40, 40)); im.save(f"{out}/{n}-compare.png")
print("done")
