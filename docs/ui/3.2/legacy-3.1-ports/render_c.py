"""Mockup C: problem-file list on the results page (port of 3.1.1 9d41228)."""
import os, sys, tempfile
from pathlib import Path
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, sys.argv[1])
OUT = Path(sys.argv[2]); OUT.mkdir(parents=True, exist_ok=True)
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (QApplication, QDialog, QHBoxLayout, QLabel, QTableWidget, QTableWidgetItem,
                             QVBoxLayout, QHeaderView, QWidget)
app = QApplication.instance() or QApplication([])
from PIL import Image
from v3_components import ButtonVariant, V3Button, apply_v3_theme
from v3_clipart_flow import ClipartRunRequest
from v3_project_state import CommonProjectData, ProjectMode, ProjectState
from v3_run_queue import RunQueueSession, RunResultsPage

tmp = Path(tempfile.mkdtemp())
names = ["rose_bouquet.png", "teddy_bear.png", "garden_basket.png", "tea_cup.png", "christmas_wreath.png"]
src = []
for n in names:
    p = tmp / n; Image.new("RGBA", (64, 64), (200, 120, 90, 255)).save(p); src.append(p)
out = tmp / "output"; out.mkdir()
state = ProjectState(mode=ProjectMode.PROCESSING, common=CommonProjectData(work_dir=str(tmp)))
req = ClipartRunRequest(mode="mode2_process", work_dir=str(tmp), settings={"output_dir": str(out)},
                        selected_files=[str(p) for p in src])
session = RunQueueSession(req, ProjectMode.PROCESSING)
def ev(i, status, **kw):
    session.handle_item_progress({"item_index": i, "total_items": 5, "stage": kw.pop("stage", "export"), "status": status, **kw})
for i in (1, 3, 5):
    o = out / f"{names[i-1][:-4]}_ready.png"; Image.new("RGBA", (64, 64), (20, 30, 40, 255)).save(o)
    ev(i, "succeeded", output_path=str(o))
ev(2, "failed", stage="remove_background", message="Fal.ai: файл больше 8 МБ")
ev(4, "cancelled", message="Остановлено пользователем")
session.handle_finished()
page = RunResultsPage(state); page.set_session(session)
# Proposed: one more button in the utility row, only when there are failed or stopped files.
problems = V3Button("Проблемные файлы (2)", ButtonVariant.SECONDARY)
page.check_transparency_button.parentWidget().layout().addWidget(problems)
apply_v3_theme(page); page.resize(1120, 780); page.show()
for _ in range(5): app.processEvents()
page.grab().save(str(OUT / "C1-results-proposed.png"))

dialog = QDialog(); dialog.setWindowTitle("Проблемные файлы")
apply_v3_theme(dialog)
lay = QVBoxLayout(dialog); lay.setContentsMargins(20, 18, 20, 18); lay.setSpacing(10)
title = QLabel("Проблемные файлы — 2 из 5"); title.setStyleSheet("font-size:18px;font-weight:bold;color:#e4edf6")
lay.addWidget(title)
hint = QLabel("Готовые файлы уже в папке результатов. Ниже — что не получилось и почему. "
              "«Доделать оставшиеся» повторит только эти файлы; уже оплаченные этапы повторно не оплачиваются.")
hint.setWordWrap(True); hint.setStyleSheet("color:#a6b5c8"); lay.addWidget(hint)
rows = [("Ошибка", "teddy_bear.png", "Удаление фона (Fal.ai)", "Файл больше 8 МБ — уменьшите его или выберите другой способ", "1"),
        ("Остановлен", "tea_cup.png", "Апскейл", "Остановлено пользователем", "1")]
table = QTableWidget(len(rows), 5)
table.setHorizontalHeaderLabels(["Итог", "Файл", "Этап", "Причина", "Попыток"])
for r, row in enumerate(rows):
    for c, v in enumerate(row):
        it = QTableWidgetItem(v)
        if c == 0:
            it.setForeground(Qt.GlobalColor.red if v == "Ошибка" else Qt.GlobalColor.yellow)
        table.setItem(r, c, it)
table.verticalHeader().hide()
h = table.horizontalHeader(); h.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
for c in (0, 1, 2, 4): h.setSectionResizeMode(c, QHeaderView.ResizeMode.ResizeToContents)
table.setStyleSheet("QTableWidget{background:#16202e;color:#e4edf6;gridline-color:#2b3a4e;border:1px solid #2b3a4e}"
                    "QHeaderView::section{background:#1d2a3b;color:#a6b5c8;padding:6px;border:none}")
lay.addWidget(table, 1)
note = QLabel("В список не попадают полные пути к файлам. Сохраняется в текстовый файл UTF-8.")
note.setStyleSheet("color:#74869a;font-size:12px"); lay.addWidget(note)
buttons = QHBoxLayout()
for text, variant in (("Скопировать список", ButtonVariant.SECONDARY), ("Сохранить как .txt…", ButtonVariant.SECONDARY)):
    buttons.addWidget(V3Button(text, variant))
buttons.addStretch(1); buttons.addWidget(V3Button("Закрыть", ButtonVariant.PRIMARY))
lay.addLayout(buttons)
dialog.resize(820, 420); dialog.show()
for _ in range(5): app.processEvents()
dialog.grab().save(str(OUT / "C2-problem-files-dialog.png"))
os._exit(0)
