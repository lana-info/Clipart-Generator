"""Снимки настоящего экрана ПОСЛЕ правки A (2026-10-30), код без подмены. Запуск: python capture_actual.py <repo> <out>"""
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
from studio_set_export_ui import SetExportDialog
from v3_components import ButtonVariant, V3Button, apply_v3_theme

tmp = Path(tempfile.mkdtemp())
paths, reports = [], []
for n in range(1, 7):
    p = tmp / f"gusenok_nabor_{n:02d}_ready.png"
    im = Image.new("RGBA", (300, 300), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.ellipse((60, 60, 240, 240), fill=(250, 240, 220, 255))
    d.ellipse((180, 95, 215, 130), fill=(245, 170, 80, 255))
    im.save(p)
    paths.append(p)
    reports.append(AlphaQcReport(str(p.resolve()), "ok", (), 300, 300))

# Так приложение приходит на шаг «Наборы» после прогона: картинки готовы, «Ок» ещё не поставлен.
panel = SetExportDialog([], review_paths=paths, quality_reports=reports,
                        embedded=True, project_name="Гусёнок", membership={})
panel.enable_marks({str(p.resolve()): "unchecked" for p in paths})

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

print("итог:", repr(panel.summary_counts.text()))
print("подсказка видна:", not panel.empty_hint.isHidden(), repr(panel.empty_hint.text()))
print("панель напоминания видна:", not panel.quality_panel.isHidden(), "|", repr(panel.quality_summary_label.text()))
frame.grab().save(str(OUT / "наборы-после.png"))
os._exit(0)
