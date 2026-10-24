"""Real screen (not a mockup): the implemented «Проверка PNG перед экспортом». Run: python capture_actual.py <repo> <out>."""
import os, sys, tempfile
from pathlib import Path
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, sys.argv[1]); OUT = Path(sys.argv[2]); OUT.mkdir(parents=True, exist_ok=True)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import QApplication, QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget
app = QApplication.instance() or QApplication([])
from PIL import Image, ImageDraw, ImageFont
from studio_alpha_qc import AlphaQcIssue, AlphaQcReport
from studio_set_export_ui import SetExportDialog
from v3_components import ButtonVariant, V3Button, apply_v3_theme

tmp = Path(tempfile.mkdtemp())
names = ["gusenok_imeninnik_v_01", "gusenok_s_obemnoy_02", "gusenok_v_solomennoy_03", "gusenok_s_prazdnichnym_04",
         "gusenok_s_vintazhnoy_05", "gusenok_s_podarochnoy_06", "gusenok_s_vetochkoy_07", "polukruglyy_venok_podkova_08",
         "tsvetochnyy_venok_09", "pryamougolnaya_ramka_10", "nizhniy_bordyur_11", "uglovaya_girlyanda_12"]
paths, reports = [], []
for i, n in enumerate(names):
    p = tmp / f"{n}_ready.png"
    im = Image.new("RGBA", (300, 300), (0, 0, 0, 0)); d = ImageDraw.Draw(im)
    if "venok" in n:
        d.ellipse((-20, 40, 320, 380), outline=(120, 170, 110, 255), width=40)  # touches the edge
    else:
        d.ellipse((60, 60, 240, 240), fill=(250, 240, 220, 255)); d.ellipse((190, 90, 225, 125), fill=(245, 170, 80, 255))
    im.save(p); paths.append(p)
    if "venok_podkova" in n:
        reports.append(AlphaQcReport(str(p.resolve()), "review", (AlphaQcIssue(
            "touches_edge", "review", "Видимые пиксели доходят до края холста — край рисунка может быть обрезан.",
            "Откройте в проверке прозрачности и посмотрите край; если всё в порядке — оставьте как есть."),), 300, 300))
    else:
        reports.append(AlphaQcReport(str(p.resolve()), "ok", (), 300, 300))


panel = SetExportDialog(paths, quality_reports=reports, embedded=True, project_name="Гусёнок")
panel._show_quality_review()
frame = QWidget(); apply_v3_theme(frame)
lay = QVBoxLayout(frame); lay.setContentsMargins(16, 12, 16, 12)
lay.addWidget(panel, 1)
foot = QFrame(); foot.setProperty("v3Card", True); fl = QHBoxLayout(foot)
fl.addWidget(QLabel("Проект сохранён")); fl.addStretch(1)
for t, v in (("Назад", ButtonVariant.SECONDARY), ("Сохранить проект", ButtonVariant.SECONDARY),
             ("Создать ZIP-наборы", ButtonVariant.PRIMARY)):
    fl.addWidget(V3Button(t, v))
lay.addWidget(foot)
frame.resize(1120, 780); frame.show()
for _ in range(6): app.processEvents()
frame.grab().save(str(OUT / "export-png-check-actual-1120x780.png"))
os._exit(0)
