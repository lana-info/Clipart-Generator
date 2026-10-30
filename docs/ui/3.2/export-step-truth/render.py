"""Макет «было/стало» для правки A (2026-10-30): шаг «Наборы», картинки готовы, ни одна не подтверждена «Ок».

Снимки настоящего экрана: тот же SetExportDialog, что в приложении. «было» — код 3.2.52;
«стало» — предлагаемое поведение, нарисованное поверх тех же виджетов.
Запуск: python render.py <repo> <out>
"""
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
names = [f"gusenok_nabor_{n:02d}" for n in range(1, 7)]
paths, reports = [], []
for n in names:
    p = tmp / f"{n}_ready.png"
    im = Image.new("RGBA", (300, 300), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.ellipse((60, 60, 240, 240), fill=(250, 240, 220, 255))
    d.ellipse((180, 95, 215, 130), fill=(245, 170, 80, 255))
    im.save(p)
    paths.append(p)
    reports.append(AlphaQcReport(str(p.resolve()), "ok", (), 300, 300))

TOTAL = 6


def build(proposed: bool):
    # Так приходит приложение на этот шаг, когда только что сгенерированы 6 картинок и «Ок» ещё не поставлен:
    # в наборы (paths) не попадает ничего, а в проверке (review_paths) лежат все шесть.
    panel = SetExportDialog([], review_paths=paths, quality_reports=reports,
                            embedded=True, project_name="Гусёнок", membership={})
    panel.enable_marks({str(p.resolve()): "unchecked" for p in paths})
    panel._show_summary()
    if proposed:
        panel.summary_counts.setText(f"Готово картинок: {TOTAL} · в наборах: 0 · наборов: 0")
        panel.quality_summary_label.setText(f"Не помечено «Ок»: {TOTAL}")
        panel.quality_panel.setProperty("state", "warning")
        panel.quality_panel.style().unpolish(panel.quality_panel)
        panel.quality_panel.style().polish(panel.quality_panel)
        panel.quality_panel.setVisible(True)
        panel.review_quality_button.setVisible(True)
        panel.empty_hint.setText(
            "В наборы попадут только картинки, подтверждённые «Ок»."
        )
        panel.empty_hint.setVisible(True)
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
    return frame


before = build(False)
print("БЫЛО: итог =", repr(before.findChild(QWidget).summary_counts.text() if False else ""))
before.grab().save(str(OUT / "наборы-было.png"))
after = build(True)
after.grab().save(str(OUT / "наборы-стало.png"))

pages = [Image.open(OUT / "наборы-было.png").convert("RGB"),
         Image.open(OUT / "наборы-стало.png").convert("RGB")]
pages[0].save(OUT / "шаг-наборы-до-после-20261030.pdf", save_all=True, append_images=pages[1:])
os._exit(0)
