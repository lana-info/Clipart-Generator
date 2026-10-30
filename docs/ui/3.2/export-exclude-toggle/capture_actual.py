"""Снимки настоящего экрана ПОСЛЕ правки 2026-10-30 (код без подмены). Запуск: python capture_actual.py <repo> <out>"""
import os, sys, tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, sys.argv[1])
OUT = Path(sys.argv[2])
OUT.mkdir(parents=True, exist_ok=True)

from PyQt6.QtWidgets import QApplication, QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget

app = QApplication.instance() or QApplication([])

from PIL import Image, ImageDraw
from studio_alpha_qc import AlphaQcReport
from studio_export_membership import validate_export_membership
from studio_set_export_ui import SetExportDialog
from v3_components import ButtonVariant, V3Button, apply_v3_theme

tmp = Path(tempfile.mkdtemp())
names = ["gusenok_imeninnik_01", "venok_podkova_02", "gusenok_s_bantom_03", "ramka_tsvety_04",
         "bordyur_listya_05", "ugol_girlyanda_06"]
paths, reports = [], []
for n in names:
    p = tmp / f"{n}_ready.png"
    im = Image.new("RGBA", (300, 300), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    if "venok" in n:
        d.ellipse((20, 30, 280, 290), outline=(120, 170, 110, 255), width=38)
    elif "ramka" in n:
        d.rectangle((30, 40, 270, 260), outline=(240, 180, 90, 255), width=30)
    elif "bordyur" in n:
        d.arc((10, 10, 290, 290), 200, 340, fill=(150, 200, 120, 255), width=34)
    elif "ugol" in n:
        d.line(((20, 20), (120, 120), (240, 60)), fill=(230, 160, 200, 255), width=28)
    else:
        d.ellipse((70, 70, 230, 230), fill=(250, 240, 220, 255))
        d.ellipse((180, 95, 215, 130), fill=(245, 170, 80, 255))
    im.save(p)
    paths.append(p)
    reports.append(AlphaQcReport(str(p.resolve()), "ok", (), 300, 300))

MARKS = {0: "ok", 1: "ok", 2: "bad_cutout", 3: "ok", 4: "ok", 5: "unchecked"}
EXCLUDED = 2
key = str(paths[EXCLUDED].resolve())

membership = validate_export_membership({str(p.resolve()): {"title": "Мини", "included": True} for p in paths})
for link in membership[key]["memberships"]:
    link["included"] = False

panel = SetExportDialog(paths, membership=membership, quality_reports=reports, embedded=True, project_name="Гусёнок")
panel.enable_marks({str(p.resolve()): MARKS[i] for i, p in enumerate(paths)})
panel._show_quality_review()
panel.quality_list.setCurrentRow(EXCLUDED)
panel._quality_selected(EXCLUDED)

frame = QWidget()
apply_v3_theme(frame)
lay = QVBoxLayout(frame)
lay.setContentsMargins(16, 12, 16, 12)
lay.addWidget(panel, 1)
foot = QFrame()
foot.setProperty("v3Card", True)
fl = QHBoxLayout(foot)
fl.addWidget(QLabel("Проект сохранён"))
fl.addStretch(1)
for label, variant in (("Назад", ButtonVariant.SECONDARY), ("Сохранить проект", ButtonVariant.SECONDARY),
                       ("Создать ZIP-наборы", ButtonVariant.PRIMARY)):
    fl.addWidget(V3Button(label, variant))
lay.addWidget(foot)
frame.resize(1120, 780)
frame.show()
for _ in range(6):
    app.processEvents()

print("исключена: кнопка =", panel.quality_exclude_button.text(),
      "; нажимается =", panel.quality_exclude_button.isEnabled(),
      "; правка прозрачности нажимается =", panel.quality_fix_button.isEnabled())
print("подсказка строки:", panel.quality_list.item(EXCLUDED).toolTip())
frame.grab().save(str(OUT / "после-исключено.png"))

# та же кнопка возвращает картинку в наборы
panel.quality_exclude_button.click()
panel.quality_list.setCurrentRow(EXCLUDED)
panel._quality_selected(EXCLUDED)
print("вернули: кнопка =", panel.quality_exclude_button.text(),
      "; в наборах =", panel._path_is_active(key),
      "; подсказка строки:", panel.quality_list.item(EXCLUDED).toolTip())
for _ in range(4):
    app.processEvents()
frame.grab().save(str(OUT / "после-вернули-в-наборы.png"))
os._exit(0)
