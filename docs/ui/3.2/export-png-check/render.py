"""Mockup: Auto Clipart export — «Проверка PNG перед экспортом» (owner remark 2026-10-23)."""
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


def window(proposed):
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
    if proposed:
        page = panel.quality_page
        # one «Создать ZIP-наборы» — the one in the window footer
        panel.quality_export_button.hide()
        panel.quality_back_button.setText("← К наборам")
        page.layout().itemAt(0).widget().setText("Проверка PNG перед экспортом")
        page.layout().itemAt(1).widget().hide()   # owner 2026-10-23: no explanatory captions
        panel.quality_page_summary_label.setText("Нужно посмотреть: 1 из 12. Остальные 11 — готовы.")
        # filter: problems first, auto-selected
        chips = QHBoxLayout()
        chips.addWidget(V3Button("Нужно посмотреть (1)", ButtonVariant.PRIMARY))
        chips.addWidget(V3Button("Все (12)", ButtonVariant.SECONDARY)); chips.addStretch(1)
        page.layout().insertLayout(3, chips)
        for row in range(panel.quality_list.count() - 1, -1, -1):
            if "Проверьте" not in panel.quality_list.item(row).text():
                panel.quality_list.takeItem(row)
        panel.quality_list.setCurrentRow(0)
        panel.quality_issue_title.setText("Проверьте края")
        # picture of the selected PNG on a checker background
        pic = QLabel(); pic.setAlignment(Qt.AlignmentFlag.AlignCenter)
        bg = Image.new("RGB", (220, 220), (255, 255, 255)); bd = ImageDraw.Draw(bg)
        for y in range(0, 220, 14):
            for x in range(0, 220, 14):
                if (x // 14 + y // 14) % 2: bd.rectangle((x, y, x + 13, y + 13), fill=(214, 220, 228))
        src = Image.open(paths[7]).resize((220, 220)); bg.paste(src, (0, 0), src)
        bg.save(OUT / "_pic.png"); pic.setPixmap(QPixmap(str(OUT / "_pic.png")))
        detail = panel.quality_issue_title.parentWidget().layout()
        detail.insertWidget(1, pic)
        panel.quality_fix_button.setText("Открыть в проверке прозрачности")
        panel.quality_exclude_button.setText("Исключить из наборов")
    frame.resize(1120, 780); frame.show()
    for _ in range(6): app.processEvents()
    return frame.grab()


def to_pil(pixmap, name):
    pixmap.save(str(OUT / name)); return Image.open(OUT / name).convert("RGB")


a = to_pil(window(False), "_a.png"); b = to_pil(window(True), "_b.png")
f = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 18)
out = Image.new("RGB", (a.width * 2 + 24, a.height + 40), (8, 12, 20)); d = ImageDraw.Draw(out)
out.paste(a, (0, 40)); out.paste(b, (a.width + 24, 40))
d.text((14, 9), "СЕЙЧАС", font=f, fill=(240, 180, 90)); d.text((a.width + 38, 9), "ПРЕДЛАГАЮ", font=f, fill=(45, 212, 191))
out.save(OUT / "export-png-check.png")
for n in ("_a.png", "_b.png", "_pic.png"): (OUT / n).unlink()
os._exit(0)
