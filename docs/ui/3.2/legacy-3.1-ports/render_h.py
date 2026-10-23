"""Mockup H: licence activation error shows a safe support code with «Скопировать код ошибки» (port of 3.1.4 ba0c153)."""
import os, sys
from pathlib import Path
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, sys.argv[1])
OUT = Path(sys.argv[2]); OUT.mkdir(parents=True, exist_ok=True)
from PyQt6.QtWidgets import QApplication, QLabel, QPushButton
app = QApplication.instance() or QApplication([])
from v3_components import apply_v3_theme
from v3_license import LicenseDialog

class Gate:
    status_text = "Лицензия не активирована"

def shot(name, proposed):
    d = LicenseDialog(Gate())
    d.license_key_input.setText("")
    d.status_label.setText("Не удалось связаться с сервером лицензий. Проверьте интернет и повторите.")
    if proposed:
        lay = d.layout()
        code = QLabel("Код ошибки: license_ssl_verification"); code.setStyleSheet("color:#f5b45a;font-weight:bold")
        lay.insertWidget(lay.indexOf(d.status_label) + 1, code)
        lay.insertWidget(lay.indexOf(code) + 1, QPushButton("Скопировать код ошибки"))
        hint = QLabel("Код не содержит ключа и личных данных — его можно отправить в поддержку.")
        hint.setWordWrap(True); hint.setStyleSheet("color:#74869a;font-size:12px")
        lay.insertWidget(lay.indexOf(code) + 2, hint)
    apply_v3_theme(d); d.resize(520, 260 if proposed else 200); d.show()
    for _ in range(5): app.processEvents()
    d.grab().save(str(OUT / name))

shot("H0-licence-current.png", False)
shot("H1-licence-proposed.png", True)
os._exit(0)
