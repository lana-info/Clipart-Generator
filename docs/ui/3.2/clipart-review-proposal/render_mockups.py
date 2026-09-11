"""Clipart-only approval mockups; no production widgets changed or API calls."""
import importlib.util
import os
from pathlib import Path
import tempfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
OUT = Path(__file__).parent
# Reuse drawing primitives, not the rejected screen or its mixed-type workflow.
spec = importlib.util.spec_from_file_location("mockup_primitives", OUT.parent / "result-kind-proposal/render_mockups.py")
ui = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ui)
from PyQt6.QtWidgets import QApplication, QWidget


def render(app, state):
    window = QWidget()
    window.setFixedSize(1120, 780)
    window.setStyleSheet(f"background:{ui.BG};")
    empty = state == "empty"
    conflict = state == "conflict"
    unavailable = state == "missing-key"
    unknown = state == "unknown-price"
    ui.box(window, 0, 0, 1120, 62, "#111b2a", "#111b2a")
    ui.label(window, 24, 12, 168, 36, "VIBIX  Studio", 14, bold=True)
    ui.label(window, 216, 12, 490, 36, "Модуль Clipart  /  Рождественский сад", 13, ui.ACCENT)
    ui.button(window, 801, 11, 140, "Каталог Studio")
    ui.button(window, 953, 11, 143, "Настройки API")
    ui.label(window, 24, 72, 1070, 24, "МАКЕТ · 1120 × 780 · Только модуль Clipart · Данные и цены демонстрационные", 10, ui.MUTED)
    ui.label(window, 24, 109, 1040, 40, "Проверьте клипарты перед запуском", 23, bold=True)
    ui.label(window, 24, 157, 1060, 28, "1  Тема и стиль     →     2  Клипарты и промпты     →     3  Проверка и запуск", 12, ui.ACCENT)
    left = ui.box(window, 24, 202, 638, 462)
    ui.label(left, 20, 14, 590, 35, "Клипарты набора", 16, bold=True)
    ui.label(left, 20, 55, 592, 43, "Результат: отдельные PNG с прозрачным фоном.\nВыберите строку, чтобы проверить её обработку.", 11, ui.MUTED)
    if empty:
        ui.label(left, 26, 143, 584, 43, "Добавьте клипарты в набор", 20, bold=True)
        ui.label(left, 26, 198, 570, 74, "Выберите тему, палитру и предметы на предыдущем шаге. Пресет сам по себе не запускает генерацию.", 13, ui.MUTED)
        ui.button(left, 26, 294, 245, "Настроить набор")
    else:
        ui.label(left, 23, 109, 55, 27, "№", 10, ui.MUTED)
        ui.label(left, 74, 109, 355, 27, "КЛИПАРТ", 10, ui.MUTED)
        ui.label(left, 452, 109, 153, 27, "ПРОМПТ", 10, ui.MUTED)
        for i, name in enumerate(("Пуансеттия", "Еловая ветка", "Подарочная коробка")):
            row = ui.box(left, 12, 145 + 64 * i, 614, 55, "#153b40" if i == 0 else "#182232", ui.ACCENT if i == 0 else ui.LINE)
            ui.label(row, 12, 9, 40, 35, f"0{i + 1}", 11, ui.MUTED)
            ui.label(row, 62, 9, 365, 35, name, 13, bold=i == 0)
            ui.label(row, 440, 9, 163, 35, "Проверить" if conflict and i == 0 else "Подготовлен", 11, "#f0c38a" if conflict and i == 0 else ui.MUTED)
        ui.label(left, 22, 350, 589, 35, "Модель: GPT Image 2 через KIE · 3 изображения", 12)
        ui.button(left, 22, 404, 220, "Изменить промпт")
        ui.label(left, 263, 402, 350, 44, "Модель и размер задаются\nв настройках генерации Clipart.", 10, ui.MUTED)
    right = ui.box(window, 680, 202, 416, 462)
    ui.label(right, 20, 14, 373, 35, "Обработка клипарта", 16, bold=True)
    ui.label(right, 20, 55, 372, 30, "Выберите клипарт слева" if empty else "01 · Пуансеттия", 13, ui.ACCENT)
    if empty:
        ui.label(right, 20, 114, 368, 107, "Покажем палитру, автоматически выбранный фон и шаги обработки. Общие настройки набора остаются на предыдущем шаге.", 13, ui.MUTED)
    else:
        ui.label(right, 20, 98, 370, 25, "ПАЛИТРА КЛИПАРТА", 10, ui.MUTED)
        for i, color in enumerate(("#ae3949", "#d9888e", "#efdfbb", "#386554", "#193d35")):
            ui.box(right, 20 + 42*i, 136, 32, 25, color, color)
        ui.label(right, 238, 127, 164, 42, "Изменить в стиле", 10, ui.MUTED)
        panel = ui.box(right, 16, 180, 384, 104, "#342c23" if conflict else "#15343b", "#c99b59" if conflict else "#297978")
        ui.label(panel, 12, 8, 356, 29, "Конфликт фона" if conflict else "Фон для генерации · Авто · синий", 11, "#f0c38a" if conflict else ui.INK, True)
        ui.label(panel, 12, 42, 356, 52, "В промпте задан белый фон,\nа для удаления выбран синий." if conflict else "Подбираем отдельно для каждого клипарта.\nПалитра помогает избежать совпадений.", 10, ui.MUTED)
        for i, text in enumerate(("1  Генерация клипарта", "2  Проверка и удаление фона", "3  Проверка края и экспорт PNG")):
            ui.label(right, 20, 300+34*i, 373, 30, text, 11)
        ui.label(right, 20, 407, 373, 48, "Если PNG уже имеет прозрачный фон,\nпроверяем alpha без повторного вырезания.", 10, ui.MUTED)
    note = "Добавьте клипарты, чтобы рассчитать запуск." if empty else "Исправьте конфликт фона перед запуском набора." if conflict else "Для выбранной модели не настроен ключ KIE. Запуск недоступен." if unavailable else "Стоимость пока неизвестна. Обновите оценку перед запуском." if unknown else "Пример оценки: $0.09 за 3 изображения · локальное удаление фона $0"
    ui.label(window, 24, 676, 1072, 33, note, 12, "#f0c38a" if conflict or unavailable or unknown else ui.INK)
    ui.label(window, 24, 718, 655, 43, "Исходники сохраняются. Сомнительные края требуют просмотра.", 10, ui.MUTED)
    ui.button(window, 696, 722, 167, "Назад к набору")
    action = "Настроить ключ" if unavailable else "Исправить промпт" if conflict else "Обновить оценку" if unknown else "Создать клипарты" if empty else "Создать 3 клипарта"
    ui.button(window, 878, 722, 218, action, primary=True, disabled=empty)
    window.show()
    app.processEvents()
    assert window.grab().save(str(OUT / f"{state}-1120x780.png"))
    window.close()


if __name__ == "__main__":
    with tempfile.TemporaryDirectory(prefix="vibix-clipart-proposal-") as folder:
        os.environ["LOCALAPPDATA"] = folder
        app = QApplication.instance() or QApplication([])
        for state in ("default", "empty", "conflict", "unknown-price", "missing-key"):
            render(app, state)
    print("Rendered 5 Clipart-only approval mockups; no runtime edits or API calls.")
