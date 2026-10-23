"""Mockup D: Fal.ai Background Remover 8 MB preflight on «Проверка и запуск» (port of 3.1.1 6a67834)."""
import os, sys, tempfile
from pathlib import Path
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, sys.argv[1]); sys.path.insert(0, str(Path(sys.argv[1]) / "tests"))
OUT = Path(sys.argv[2]); OUT.mkdir(parents=True, exist_ok=True)
from PyQt6.QtWidgets import QApplication
app = QApplication.instance() or QApplication([])
from PIL import Image
from studio_workflow_host import WorkflowHost
from test_v3_processing_flow import WorkerFactory
from v3_components import apply_v3_theme
from v3_processing_flow import apply_processing_recipe, install_processing_flow
from v3_project_state import ProjectMode, ProjectState, StepId
from v3_wizard import AppShell

tmp = Path(tempfile.mkdtemp())
files = []
for n in ["rose_bouquet.png", "teddy_bear_upscaled.png", "garden_basket.png", "tea_cup_upscaled.png", "wreath.png"]:
    p = tmp / n; Image.new("RGB", (64, 64), (120, 80, 30)).save(p); files.append(str(p))
state = ProjectState(mode=ProjectMode.PROCESSING)
state.common.work_dir = str(tmp)
state.processing.selected_files = files
apply_processing_recipe(state, "basic_enhancement")
ops = state.processing.operations
ops.remove_background = True; ops.remove_background_provider = "fal"
state.current_step_by_mode[ProjectMode.PROCESSING] = StepId.REVIEW_RUN
shell = AppShell(state)
rt = {"fal_api_key": "x"}
controller = install_processing_flow(WorkflowHost(shell, "processing", runtime_settings_provider=lambda: rt,
                                                  worker_factory=WorkerFactory()))
page = controller.review_page
controller._refresh_preflight()
apply_v3_theme(shell); shell.resize(1120, 780); shell.show()
for _ in range(5): app.processEvents()
shell.grab().save(str(OUT / "D0-review-current.png"))
# Proposed: blocking card that names the files and offers three ways out; Run disabled.
page.requirements_label.setText(
    "Запуск остановлен: 2 файла больше 8 МБ — Fal.ai Background Remover их не примет, а остальные "
    "файлы пакета зря ждали бы.\n"
    "  • teddy_bear_upscaled.png — 14,2 МБ\n"
    "  • tea_cup_upscaled.png — 11,7 МБ\n"
    "Что сделать: уменьшить эти файлы, убрать их из списка (шаг «Файлы») или выбрать другой способ удаления "
    "фона (шаг «Обработка»). Файлы, у которых прозрачность уже есть, не проверяются.")
page.requirements_label.setProperty("state", "error")
page.requirements_label.show()
page.requirements_label.style().unpolish(page.requirements_label); page.requirements_label.style().polish(page.requirements_label)
page.requirements_label.setStyleSheet("QLabel{background:rgba(120,30,40,90);border:1px solid #f06e6e;"
                                      "border-radius:8px;padding:10px;color:#ffd9d9}")
from PyQt6.QtWidgets import QPushButton
for b in shell.findChildren(QPushButton):
    if b.text() == "Запустить":
        b.setEnabled(False)
for _ in range(5): app.processEvents()
shell.grab().save(str(OUT / "D1-review-proposed.png"))
os._exit(0)
