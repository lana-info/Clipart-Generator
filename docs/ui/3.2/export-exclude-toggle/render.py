"""Макет «было/стало» для правки 2026-10-30: исключённую из наборов картинку можно вернуть.

Снимаются настоящие экраны (не рисунки): тот же SetExportDialog, что в приложении.
«было» — код как в 3.2.52; «стало» — предлагаемое поведение, нарисованное поверх тех же виджетов.

Запуск: python render.py <repo> <out>
"""
import os, sys, tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, sys.argv[1])
OUT = Path(sys.argv[2])
OUT.mkdir(parents=True, exist_ok=True)

from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QColor, QFont, QIcon, QPainter, QPen, QPixmap
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
for i, n in enumerate(names):
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
EXCLUDED = 2  # the picture the owner excluded from the sets; it also carries «Брак вырезания»


def build(proposed: bool):
    membership = validate_export_membership({str(p.resolve()): {"title": "Мини", "included": True} for p in paths})
    key = str(paths[EXCLUDED].resolve())
    for link in membership[key]["memberships"]:
        link["included"] = False  # the owner pressed «Исключить из наборов»
    panel = SetExportDialog(paths, membership=membership, quality_reports=reports,
                            embedded=True, project_name="Гусёнок")
    panel.enable_marks({str(p.resolve()): MARKS[i] for i, p in enumerate(paths)})

    if proposed:
        original_icon = panel._quality_icon

        def badge_icon(ik, report, active, viewed):
            """Метка остаётся видна и у исключённой картинки; исключение — отдельным значком в левом верхнем углу."""
            size = panel.QUALITY_THUMB
            picture = panel._checker_pixmap(ik, size, panel._quality_background)
            canvas = QPixmap(size, size)
            canvas.fill(QColor("#1b2636"))
            painter = QPainter(canvas)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            if not picture.isNull():
                painter.setOpacity(0.55 if ik == key else 1.0)
                painter.drawPixmap((size - picture.width()) // 2, (size - picture.height()) // 2, picture)
                painter.setOpacity(1.0)
            font = QFont(painter.font())
            font.setPixelSize(13)
            font.setBold(True)
            painter.setFont(font)

            def dot(x, y, fill, glyph, ink):
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QColor(fill))
                painter.drawEllipse(x, y, 22, 22)
                painter.setPen(QColor(ink))
                painter.drawText(x, y, 22, 22, int(Qt.AlignmentFlag.AlignCenter), glyph)

            mark = panel._marks.get(ik, "")
            state_dots = {"ok": ("#34d399", "✓", "#06201c"), "bad_generation": ("#f59e0b", "Г", "#1f1300"),
                          "bad_cutout": ("#a78bfa", "В", "#140a2e"), "deleted": ("#8a97a8", "✕", "#101820")}
            if mark in state_dots:
                fill, glyph, ink = state_dots[mark]
                dot(size - 25, 3, fill, glyph, ink)
            if ik == key:  # исключена из наборов: маленький знак в свободном углу
                painter.setPen(QPen(QColor("#8ea3b8"), 2))
                painter.setBrush(QColor("#2b3340"))
                painter.drawEllipse(3, 3, 18, 18)
                painter.drawLine(6, 18, 18, 6)
            painter.end()
            icon = QIcon()
            for mode in (QIcon.Mode.Normal, QIcon.Mode.Active, QIcon.Mode.Selected):
                icon.addPixmap(canvas, mode)
            return icon

        panel._quality_icon = badge_icon
        panel._show_quality_review()
        panel.quality_list.setCurrentRow(EXCLUDED)
        panel._quality_selected(EXCLUDED)
        panel.quality_exclude_button.setText("Вернуть в наборы")
        panel.quality_exclude_button.setEnabled(True)
        panel.quality_fix_button.setEnabled(True)
        panel.quality_issue_title.setText("Исключено из наборов · Брак вырезания")
        panel.quality_picture.setToolTip("Исключено из наборов · Брак вырезания")
        row = panel.quality_list.item(EXCLUDED)
        if row is not None:
            row.setToolTip(f"{paths[EXCLUDED].name} — Исключено из наборов · Брак вырезания")
    else:
        panel._show_quality_review()
        panel.quality_list.setCurrentRow(EXCLUDED)
        panel._quality_selected(EXCLUDED)
        # Qt keeps the previous look of a button switched off without an explicit repolish
        for button in (panel.quality_fix_button, panel.quality_exclude_button):
            button.style().unpolish(button)
            button.style().polish(button)
            button.update()
        print("было: «Редактировать прозрачность» нажимается =",
              panel.quality_fix_button.isEnabled(), "; «Исключить из наборов» нажимается =",
              panel.quality_exclude_button.isEnabled())

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
before.grab().save(str(OUT / "было-исключено.png"))
after = build(True)
after.grab().save(str(OUT / "стало-исключено.png"))

# one two-page PDF for viewing
pages = [Image.open(OUT / "было-исключено.png").convert("RGB"),
         Image.open(OUT / "стало-исключено.png").convert("RGB")]
pages[0].save(OUT / "исключение-из-наборов-до-после-20261030.pdf", save_all=True, append_images=pages[1:])
os._exit(0)
