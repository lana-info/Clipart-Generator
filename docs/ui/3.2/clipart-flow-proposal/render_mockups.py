"""Offline flow mockups for approval. No production widgets, files or API calls."""
import importlib.util
import os
from pathlib import Path
import tempfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
OUT = Path(__file__).parent
spec = importlib.util.spec_from_file_location(
    "mockup_primitives", OUT.parent / "result-kind-proposal/render_mockups.py"
)
ui = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ui)
from PyQt6.QtWidgets import QApplication, QWidget


STEPS = ("1  Идея", "2  Стиль", "3  Объекты", "4  Запуск", "5  Проверка", "6  Экспорт")


def header(window, step, title, subtitle):
    ui.box(window, 0, 0, 1120, 62, "#111b2a", "#111b2a")
    ui.label(window, 24, 12, 166, 36, "VIBIX  Studio", 14, bold=True)
    ui.label(window, 205, 12, 490, 36, "Модуль Clipart  /  Лесное Рождество", 13, ui.ACCENT)
    ui.button(window, 812, 11, 129, "Каталог Studio")
    ui.button(window, 953, 11, 143, "Настройки API")
    ui.label(window, 24, 72, 1068, 20, "МАКЕТ ДЛЯ СОГЛАСОВАНИЯ · 1120 × 780 · демо-данные, без запуска генерации", 10, ui.MUTED)
    ui.label(window, 24, 104, 1068, 37, title, 24, bold=True)
    ui.label(window, 24, 147, 1068, 30, subtitle, 12, ui.MUTED)
    x = 24
    for index, name in enumerate(STEPS, start=1):
        active = index == step
        ui.box(window, x, 187, 169, 34, "#153b40" if active else "#182232", ui.ACCENT if active else ui.LINE)
        ui.label(window, x + 12, 192, 145, 22, name, 11, ui.ACCENT if active else ui.MUTED, active)
        x += 181


def pill(parent, x, y, text, selected=False):
    width = max(92, 26 + len(text) * 7)
    ui.box(parent, x, y, width, 34, "#153b40" if selected else "#182232", ui.ACCENT if selected else ui.LINE)
    ui.label(parent, x + 12, y + 4, width - 20, 25, text, 11, ui.ACCENT if selected else ui.INK, selected)
    return width


def footer(window, secondary, primary, disabled=False):
    ui.label(window, 24, 724, 645, 34, "Черновик проекта сохранён локально. Генерация не начнётся без подтверждения.", 10, ui.MUTED)
    ui.button(window, 680, 721, 183, secondary)
    ui.button(window, 878, 721, 218, primary, primary=True, disabled=disabled)


def brief(window):
    header(window, 1, "Соберите идею набора", "Только то, что определяет весь набор. Детали можно изменить на следующем шаге.")
    left = ui.box(window, 24, 242, 682, 470)
    right = ui.box(window, 724, 242, 372, 470)
    ui.label(left, 20, 16, 632, 31, "Тема набора", 16, bold=True)
    ui.label(left, 20, 53, 625, 23, "О чём будут клипарты?", 11, ui.MUTED)
    ui.box(left, 20, 86, 632, 47, "#182232", ui.LINE)
    ui.label(left, 34, 94, 580, 30, "Лесные звери и зимние растения", 14)
    ui.label(left, 20, 151, 630, 24, "Контекст набора", 12, bold=True)
    pill(left, 20, 184, "Рождество", True)
    ui.label(left, 20, 226, 620, 28, "Выберите сезон или конкретный праздник, но не оба одновременно.", 10, ui.MUTED)
    ui.label(left, 20, 270, 620, 25, "Рецепт набора", 16, bold=True)
    ui.label(left, 20, 302, 622, 38, "Выберите, сколько элементов каждого типа вам нужно. Без случайного длинного списка.", 11, ui.MUTED)
    recipe = (("Главные объекты", "4"), ("Композиции", "3"), ("Венки", "2"), ("Бордюры / рамки", "2"), ("Мелкий декор", "9"))
    for i, (name, amount) in enumerate(recipe):
        x = 20 + (i % 3) * 210
        y = 342 + (i // 3) * 54
        ui.box(left, x, y, 194, 43, "#182232", ui.LINE)
        ui.label(left, x + 12, y + 5, 138, 31, name, 10)
        ui.label(left, x + 162, y + 5, 24, 31, amount, 14, ui.ACCENT, True)
    ui.label(right, 20, 18, 330, 31, "Итого", 16, bold=True)
    ui.label(right, 20, 57, 325, 48, "20 отдельных\nклипартов", 18, ui.ACCENT, True)
    ui.label(right, 20, 117, 330, 57, "На следующем экране покажем несколько вариантов состава. Ничего не будет создано сейчас.", 12, ui.MUTED)
    ui.box(right, 20, 204, 332, 116, "#15343b", "#297978")
    ui.label(right, 34, 218, 295, 24, "Следующий шаг", 12, ui.INK, True)
    ui.label(right, 34, 248, 292, 53, "Настроим технику, настроение, палитру и роли референсов.", 11, ui.MUTED)
    ui.label(right, 20, 348, 330, 65, "Можно начать с пресета Holiday или сохранить собственный рецепт для будущих наборов.", 11, ui.MUTED)
    footer(window, "Сохранить", "Настроить стиль")


def style(window):
    header(window, 2, "Задайте визуальное направление", "Стиль, настроение, палитра и референсы. Они описывают весь набор, а не один предмет.")
    left = ui.box(window, 24, 242, 538, 450)
    right = ui.box(window, 580, 242, 516, 450)
    ui.label(left, 20, 16, 492, 28, "Характер изображений", 16, bold=True)
    ui.label(left, 20, 52, 485, 22, "Техника", 11, ui.MUTED)
    pill(left, 20, 82, "Акварель", True)
    pill(left, 137, 82, "Тонкий контур")
    pill(left, 20, 128, "Мягкие линии", True)
    pill(left, 155, 128, "Без реализма")
    ui.label(left, 20, 181, 485, 22, "Настроение", 11, ui.MUTED)
    pill(left, 20, 211, "Уютное", True)
    pill(left, 122, 211, "Сказочное")
    pill(left, 20, 257, "Спокойное", True)
    ui.label(left, 20, 307, 485, 22, "Палитра", 11, ui.MUTED)
    for i, color in enumerate(("#b34351", "#d68c88", "#f0dfb9", "#3e6956", "#243f37")):
        ui.box(left, 20 + i * 46, 338, 35, 28, color, color)
    ui.button(left, 20, 390, 218, "Изменить палитру")
    ui.label(left, 257, 391, 238, 35, "Палитра предметов не равна техническому chroma-фону.", 10, ui.MUTED)
    ui.label(right, 20, 16, 470, 28, "Референсы", 16, bold=True)
    ui.label(right, 20, 52, 468, 37, "Назначьте, что брать из каждого изображения. Его нельзя отправить модели без явного выбора.", 10, ui.MUTED)
    refs = (("Референс 01", "Техника · настроение"), ("Референс 02", "Палитра · композиция"), ("Референс 03", "Персонаж · поза"))
    for i, (name, roles) in enumerate(refs):
        y = 105 + i * 73
        row = ui.box(right, 14, y, 488, 62, "#182232", ui.LINE)
        ui.box(row, 12, 12, 38, 38, "#5d7a75", "#5d7a75")
        ui.label(row, 64, 8, 160, 23, name, 12, bold=True)
        ui.label(row, 64, 31, 260, 21, roles, 10, ui.ACCENT)
        ui.button(row, 386, 11, 88, "Роли")
    ui.button(right, 20, 342, 188, "Добавить референс")
    ui.label(right, 20, 393, 470, 32, "Можно выделить область, если на референсе несколько предметов.", 10, ui.MUTED)
    footer(window, "К идее", "К настройке объектов")


def plans(window):
    header(window, 3, "Выберите вариант состава", "Все варианты следуют вашему рецепту. Один можно отредактировать перед созданием prompt’ов.")
    ui.label(window, 24, 241, 1070, 28, "20 элементов · Лесные звери · Рождество · зима", 12, ui.ACCENT, True)
    cards = (
        ("Сбалансированный", "4 главных · 3 композиции · 2 венка\n2 рамки · 9 мелких деталей", "Лучший старт", True),
        ("Больше героев", "6 главных · 2 композиции · 1 венок\n1 рамка · 10 мелких деталей", "Изменённый баланс", False),
        ("Больше оформления", "3 главных · 3 композиции · 3 венка\n3 рамки · 8 мелких деталей", "Для бумажных наборов", False),
    )
    for i, (name, content, note, chosen) in enumerate(cards):
        card = ui.box(window, 24 + i * 366, 287, 348, 282, "#153b40" if chosen else "#1f2937", ui.ACCENT if chosen else ui.LINE)
        ui.label(card, 20, 20, 302, 31, name, 17, bold=True)
        ui.label(card, 20, 60, 302, 56, content, 12, ui.INK)
        ui.box(card, 20, 135, 305, 1, ui.LINE, ui.LINE)
        ui.label(card, 20, 155, 302, 28, note, 11, ui.ACCENT if chosen else ui.MUTED, chosen)
        ui.label(card, 20, 192, 302, 49, "Список предметов будет раскрыт и полностью редактируем на следующем шаге.", 10, ui.MUTED)
        if chosen:
            ui.label(card, 20, 247, 302, 22, "Выбрано", 11, ui.ACCENT, True)
    lower = ui.box(window, 24, 593, 1072, 93, "#182232", ui.LINE)
    ui.label(lower, 20, 12, 845, 27, "Сбалансированный · 20 элементов", 14, bold=True)
    ui.label(lower, 20, 42, 820, 34, "Можно поменять число ролей или удалить любой элемент. Это не создаёт новые изображения.", 11, ui.MUTED)
    ui.button(lower, 864, 27, 182, "Изменить рецепт")
    footer(window, "Назад к идее", "Открыть план")


def launch(window):
    header(window, 4, "Проверьте план и запуск", "Оставьте готовые строки, исправьте нужные. Деньги списываются только после кнопки запуска.")
    table = ui.box(window, 24, 242, 706, 449)
    side = ui.box(window, 748, 242, 348, 449)
    ui.label(table, 20, 15, 660, 28, "Сбалансированный набор · 20 элементов", 16, bold=True)
    ui.label(table, 20, 49, 660, 23, "Показаны первые 5. Остальные 15 готовы к просмотру.", 11, ui.MUTED)
    for i, (role, name) in enumerate((("Главный", "Лисёнок в шарфе"), ("Главный", "Сова с веточкой"), ("Композиция", "Подарки и ягоды"), ("Венок", "Еловый венок"), ("Рамка", "Ветки и ягоды"))):
        y = 91 + i * 56
        row = ui.box(table, 14, y, 678, 47, "#153b40" if i == 0 else "#182232", ui.ACCENT if i == 0 else ui.LINE)
        ui.label(row, 12, 7, 98, 31, role, 10, ui.ACCENT if i == 0 else ui.MUTED)
        ui.label(row, 115, 7, 337, 31, name, 12, bold=i == 0)
        ui.label(row, 468, 7, 190, 31, "Готов к запуску", 10, ui.MUTED)
    ui.button(table, 20, 384, 175, "Редактировать план")
    ui.button(table, 207, 384, 175, "Посмотреть prompt")
    ui.label(side, 20, 15, 310, 28, "Перед запуском", 16, bold=True)
    ui.label(side, 20, 57, 308, 24, "Модель: GPT Image 2 через KIE", 11)
    ui.box(side, 18, 99, 312, 116, "#15343b", "#297978")
    ui.label(side, 31, 111, 280, 27, "Фон: подберём автоматически", 12, ui.INK, True)
    ui.label(side, 31, 143, 280, 53, "Для каждого клипарта отдельно. Венки и рамки получат проверку внутренних отверстий.", 10, ui.MUTED)
    ui.label(side, 20, 244, 310, 25, "Оценка", 12, ui.MUTED)
    ui.label(side, 20, 273, 310, 33, "$0.60 за 20 изображений", 20, ui.ACCENT, True)
    ui.label(side, 20, 316, 308, 48, "Локальная обработка фона не оплачивается. Фактическая цена появится в журнале.", 10, ui.MUTED)
    ui.label(side, 20, 385, 310, 38, "После запуска можно остановить ожидающие задачи. Уже готовые сохранятся.", 10, ui.MUTED)
    footer(window, "Вернуться к плану", "Создать 20 клипартов")


def review(window):
    header(window, 5, "Проверьте готовые клипарты", "Сначала посмотрите только изображения, требующие внимания. Ready не нужно исправлять вручную.")
    left = ui.box(window, 24, 242, 708, 449)
    right = ui.box(window, 750, 242, 346, 449)
    ui.label(left, 20, 15, 650, 29, "20 результатов", 16, bold=True)
    pill(left, 20, 56, "Ready · 18", True)
    pill(left, 142, 56, "Review · 2")
    for i, (name, status, color) in enumerate((("Лисёнок в шарфе", "Ready", ui.ACCENT), ("Еловый венок", "Review · отверстие", "#f0c38a"), ("Ветки и ягоды", "Review · край", "#f0c38a"), ("Подарки и ягоды", "Ready", ui.ACCENT))):
        y = 109 + i * 66
        row = ui.box(left, 14, y, 680, 56, "#342c23" if "Review" in status else "#182232", "#c99b59" if "Review" in status else ui.LINE)
        ui.box(row, 12, 10, 36, 36, "#486a69" if "Ready" in status else "#8b633a", "#486a69" if "Ready" in status else "#8b633a")
        ui.label(row, 62, 8, 332, 39, name, 12, bold=True)
        ui.label(row, 416, 8, 163, 39, status, 11, color, True)
        ui.button(row, 585, 8, 82, "Открыть")
    ui.label(left, 20, 387, 655, 34, "Review не попадут в ZIP по умолчанию. Их можно исправить, повторить или оставить вне экспорта.", 10, ui.MUTED)
    ui.label(right, 20, 15, 305, 29, "Еловый венок", 16, bold=True)
    ui.label(right, 20, 51, 305, 26, "Нужна проверка отверстия", 11, "#f0c38a", True)
    ui.box(right, 20, 95, 305, 187, "#486a69", "#6a978e")
    ui.box(right, 105, 142, 136, 90, "#101827", "#101827")
    ui.label(right, 20, 302, 305, 47, "Фон внутри венка выглядит неоднозначно. Проверьте маску перед выдачей.", 10, ui.MUTED)
    ui.button(right, 20, 371, 305, "Открыть редактор контура", primary=True)
    footer(window, "К запуску", "Перейти к экспорту")


def export(window):
    header(window, 6, "Выдайте готовые наборы", "Каждый набор экспортируется отдельно: свои PNG, обзорный лист, manifest и ZIP.")
    ui.label(window, 24, 242, 1070, 29, "Проект «Лесное Рождество» · 2 набора", 14, ui.ACCENT, True)
    sets = (("01 · Сбалансированный", "18 Ready PNG · 2 Review исключены", "Готов к экспорту", True), ("02 · Больше героев", "20 Ready PNG · проверка завершена", "Готов к экспорту", False))
    for i, (title, detail, status, first) in enumerate(sets):
        card = ui.box(window, 24, 291 + i * 166, 1072, 140, "#153b40" if first else "#1f2937", ui.ACCENT if first else ui.LINE)
        ui.label(card, 20, 18, 500, 28, title, 17, bold=True)
        ui.label(card, 20, 53, 600, 29, detail, 12, ui.MUTED)
        ui.label(card, 20, 89, 500, 26, status, 11, ui.ACCENT, True)
        ui.label(card, 646, 22, 388, 26, "Включить: PNG · лист PNG · PDF Letter · manifest", 10, ui.MUTED)
        ui.button(card, 810, 76, 224, "Создать ZIP набора", primary=first)
    notice = ui.box(window, 24, 638, 1072, 54, "#342c23", "#c99b59")
    ui.label(notice, 16, 8, 1038, 38, "В первом наборе 2 результата Review не войдут в ZIP. Их можно исправить и экспортировать позже отдельной версией.", 11, "#f0c38a")
    footer(window, "К проверке", "Экспортировать ZIP")


def render(app, name, draw):
    window = QWidget()
    window.setFixedSize(1120, 780)
    window.setStyleSheet(f"background:{ui.BG};")
    draw(window)
    window.show()
    app.processEvents()
    assert window.grab().save(str(OUT / f"{name}-1120x780.png"))
    window.close()


if __name__ == "__main__":
    with tempfile.TemporaryDirectory(prefix="vibix-clipart-flow-") as folder:
        os.environ["LOCALAPPDATA"] = folder
        app = QApplication.instance() or QApplication([])
        for name, draw in (("01-brief", brief), ("02-style", style), ("03-plans", plans), ("04-launch", launch), ("05-review", review), ("06-export", export)):
            render(app, name, draw)
    print("Rendered six offline Clipart flow mockups; no runtime edits or API calls.")
