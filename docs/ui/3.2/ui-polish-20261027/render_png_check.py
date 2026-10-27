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



MARKS = {0: "ok", 1: "ok", 2: "bad_generation", 3: "ok", 4: "bad_cutout", 5: "ok", 6: "ok", 7: "ok", 8: "unchecked", 9: "ok", 10: "ok", 11: "ok"}
EXCLUDED = {10}
from PyQt6.QtCore import QSize
from PyQt6.QtGui import QColor, QFont, QIcon, QPainter, QPen
DOT = {"ok": "#34d399", "bad_generation": "#f59e0b", "bad_cutout": "#a78bfa"}


def build(proposed):
    reports[8] = AlphaQcReport(str(paths[8].resolve()), "review", (AlphaQcIssue("touches_edge", "review", "x", "y"),), 300, 300)
    panel = SetExportDialog(paths, quality_reports=reports, embedded=True, project_name="Гусёнок")
    panel.enable_marks({str(p.resolve()): MARKS[i] for i, p in enumerate(paths)})
    if proposed:
        old_icon = panel._quality_icon

        def dot_icon(key, report, active, viewed):
            size = panel.QUALITY_THUMB
            picture = panel._checker_pixmap(key, size, panel._quality_background)
            canvas = QPixmap(size, size); canvas.fill(QColor("#1b2636"))
            p = QPainter(canvas); p.setRenderHint(QPainter.RenderHint.Antialiasing)
            if not picture.isNull():
                p.drawPixmap((size - picture.width()) // 2, (size - picture.height()) // 2, picture)
            mark = panel._marks.get(key, "")
            idx = next(i for i, q in enumerate(paths) if str(q.resolve()) == key)
            if idx in EXCLUDED:
                p.setPen(QPen(QColor("#8ea3b8"), 2)); p.setBrush(QColor("#2b3340")); p.drawEllipse(size - 24, 4, 18, 18)
                p.drawLine(size - 21, 19, size - 9, 7)
            elif mark != "ok" and report.status != "ok" and mark not in DOT:
                p.setPen(Qt.PenStyle.NoPen); p.setBrush(QColor("#f59e0b")); p.drawEllipse(size - 24, 4, 18, 18)
                p.setPen(QColor("#1f1300")); f = QFont(p.font()); f.setPixelSize(13); f.setBold(True); p.setFont(f)
                p.drawText(size - 24, 4, 18, 18, int(Qt.AlignmentFlag.AlignCenter), "!")
            elif mark in DOT:
                p.setPen(Qt.PenStyle.NoPen); p.setBrush(QColor(DOT[mark])); p.drawEllipse(size - 24, 4, 18, 18)
            p.end()
            icon = QIcon()
            for mode in (QIcon.Mode.Normal, QIcon.Mode.Active, QIcon.Mode.Selected):
                icon.addPixmap(canvas, mode)
            return icon
        panel._quality_icon = dot_icon
    panel._show_quality_review()
    panel.quality_list.setCurrentRow(7)
    swatches = None
    if proposed:
        page = panel.quality_page
        top = page.layout().itemAt(0).layout()
        for k in range(top.count()):                       # no title, counter, filter buttons or background chips on top
            w = top.itemAt(k).widget()
            if w is not None:
                w.hide()
        for w in (panel.quality_issue_title, panel.quality_issue_text, panel.quality_action_text):
            w.hide()                                       # no «Проверьте края» and no instructions: the picture gets the room
        panel.quality_exclude_button.setText("Исключить из наборов")
        panel.quality_marks_row.layout().insertWidget(3, panel.quality_exclude_button)
        panel.quality_fix_button.setText("Редактировать прозрачность")
        panel.quality_fix_button.setSizePolicy(panel.quality_fix_button.sizePolicy().Policy.Maximum, panel.quality_fix_button.sizePolicy().Policy.Fixed)
        panel.quality_marks_row.layout().takeAt(panel.quality_marks_row.layout().count() - 1)  # stretch
        panel.quality_marks_row.layout().addStretch(1)
        panel.quality_marks_row.layout().addWidget(panel.quality_fix_button)
        panel.quality_back_button.hide()
        swatches = QWidget(); sl = QHBoxLayout(swatches); sl.setContentsMargins(0, 0, 0, 0); sl.setSpacing(8)
        lab = QLabel("Фон"); lab.setProperty("v3Small", True); sl.addWidget(lab)
        for colour in ("#ffffff", "#0b0f19", "#f2f2f2", "#6fbf73", "#E040A0", "#7db7e8"):
            b = QFrame(); b.setFixedSize(26, 26)
            b.setStyleSheet(f"background:{colour}; border:2px solid {'#2dd4bf' if colour == '#ffffff' else '#3b4b60'}; border-radius:5px;")
            sl.addWidget(b)
        sl.addStretch(1)
        # «Параметры экспорта» moved to the export step: the row below the panel now holds the background choice
        for w in panel.findChildren(QWidget):
            if hasattr(w, "text") and callable(w.text) and "Параметры экспорта" in str(w.text()):
                w.hide()
    frame = QWidget(); apply_v3_theme(frame)
    lay = QVBoxLayout(frame); lay.setContentsMargins(16, 12, 16, 12)
    lay.addWidget(panel, 1)
    if swatches is not None:
        lay.addWidget(swatches)
    foot = QFrame(); foot.setProperty("v3Card", True); fl2 = QHBoxLayout(foot)
    if proposed:
        fl2.addWidget(V3Button("← К наборам", ButtonVariant.SECONDARY))
    fl2.addWidget(QLabel("Проект сохранён")); fl2.addStretch(1)
    for t, v in (("Назад", ButtonVariant.SECONDARY), ("Сохранить проект", ButtonVariant.SECONDARY),
                 ("Создать ZIP-наборы", ButtonVariant.PRIMARY)):
        fl2.addWidget(V3Button(t, v))
    lay.addWidget(foot)
    if proposed:
        panel.setMinimumWidth(0)
    frame.resize(1120, 780); frame.show()
    for _ in range(6): app.processEvents()
    if not proposed:
        pass
    return frame


frames = []
for proposed in (False, True):
    f = build(proposed); frames.append(f)
    f.grab().save(str(OUT / ("png-check-proposed.png" if proposed else "png-check-now.png")))
os._exit(0)
