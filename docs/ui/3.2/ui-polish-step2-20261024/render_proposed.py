"""Mockup: step 2 (visual direction) with PROPOSED style cards/sections; product code untouched.
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

def new_card(self, profile, grid, index, target):
    btn = QPushButton(); btn.setCheckable(True)
    btn.setAccessibleName(profile.title); btn.setToolTip(profile.title)
    btn.setFixedHeight(104)
    row = QHBoxLayout(btn); row.setContentsMargins(10, 10, 14, 10); row.setSpacing(12)
    pv = QLabel(); pv.setFixedSize(84, 84); pv.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
    pm = QPixmap(str(B.style_preview_path(profile.key)))
    if not pm.isNull():
        pv.setPixmap(pm.scaled(84, 84, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
    pv.setStyleSheet("background:#ffffff;border-radius:6px;")
    row.addWidget(pv)
    col = QVBoxLayout(); col.setSpacing(4); col.addStretch()
    t = QLabel(profile.title); t.setWordWrap(True)
    t.setStyleSheet(f"color:{T.text};font-weight:700;font-size:14px;background:transparent;border:none;")
    d = QLabel(" · ".join(profile.best_for[:3])); d.setWordWrap(True)
    d.setStyleSheet(f"color:{T.text_muted};font-size:12px;background:transparent;border:none;")
    for w in (t, d): w.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
    col.addWidget(t); col.addWidget(d); col.addStretch()
    row.addLayout(col, 1)
    btn.setStyleSheet(
        f"QPushButton{{background:{T.surface};border:1px solid {T.border};border-radius:10px;text-align:left;padding:0;min-height:0;}}"
        f"QPushButton:hover{{border-color:{T.text_muted};}}"
        f"QPushButton:checked{{background:{T.accent_soft};border:2px solid {T.accent};}}")
    btn.clicked.connect(lambda checked=False, key=profile.key: self._select_style_profile(key))
    grid.addWidget(btn, index // self._card_columns, index % self._card_columns)
    target.append(dict(key=profile.key, title=profile.title, category=profile.category,
                       best_for=list(profile.best_for), button=btn, preview=pv, widget=btn))
B.ClipartBuilderDialog._style_card = new_card

SECTION_QSS = f"""
QGroupBox {{ border:none; background:transparent; margin-top:30px; padding-top:0; }}
QGroupBox::title {{ subcontrol-origin:margin; subcontrol-position:top left; left:0; padding:0;
  color:{T.text}; font-size:16px; font-weight:700; }}
"""
CHIP = (f"QPushButton{{background:transparent;color:{T.text};border:1px solid {T.border};border-radius:15px;"
        f"min-height:30px;padding:2px 14px;}}QPushButton:hover{{border-color:{T.text_muted};}}"
        f"QPushButton:checked{{background:{T.accent_soft};color:{T.accent};border:1px solid {T.accent};font-weight:600;}}")

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
    b.setStyleSheet(b.styleSheet() + SECTION_QSS)
    for btn in b.style_modifier_buttons.values(): btn.setStyleSheet(CHIP)
    from PyQt6.QtWidgets import QGroupBox
    for g in b.findChildren(QGroupBox):
        title = g.title(); g.setTitle("")
        g.setStyleSheet("QGroupBox{border:none;margin-top:0;padding-top:0;background:transparent;}")
        h = QLabel(title.split(" · ")[0]); h.setStyleSheet(f"color:{T.text};font-size:16px;font-weight:700;background:transparent;border:none;")
        g.layout().setContentsMargins(0, 32, 0, 0)
        h.setParent(g); h.adjustSize(); h.move(0, 2); h.show()
        if " · " in title:
            sub = QLabel(title.split(" · ")[1].capitalize()); sub.setParent(g)
            sub.setStyleSheet(f"color:{T.text_muted};font-size:12px;background:transparent;border:none;")
            sub.adjustSize(); sub.move(h.width() + 12, 6); sub.show()
    b._refresh_style_library(); app.processEvents()
    def scroll_area():
        return next(s for s in b.findChildren(QScrollArea) if s.isVisible())
    def shot(n): app.processEvents(); v.grab().save(f"{out}/{n}.png")
    shot("step-2-default")
    first = b.style_cards[1]["key"]
    b._select_style_profile(first)
    keys = list(b.style_modifier_buttons)
    for k in keys[:2]: b.style_modifier_buttons[k].setChecked(True)
    app.processEvents(); shot("step-2-selected")
    sa = scroll_area(); sa.ensureWidgetVisible(b.style_modifier_buttons[keys[0]], 20, 200); app.processEvents(); shot("step-2-selected-chips")
    c.save_timer.stop(); v.close()
print("done")
