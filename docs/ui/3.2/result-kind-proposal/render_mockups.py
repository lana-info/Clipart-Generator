"""Offline approval mockups. No production UI changes or provider requests."""
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[4]
OUT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

from PyQt6.QtWidgets import QApplication, QWidget, QLabel, QPushButton, QFrame
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont

BG, PANEL, LINE = "#101827", "#1f2937", "#354154"
INK, MUTED, ACCENT = "#eef2f7", "#a6b5c8", "#24cabb"


def label(parent, x, y, w, h, text, size=14, color=INK, bold=False):
    item = QLabel(text, parent)
    item.setGeometry(x, y, w, h)
    item.setWordWrap(True)
    item.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
    item.setStyleSheet(f"color:{color}; background:transparent; border:none; border-radius:0px;")
    item.setFont(QFont("DejaVu Sans", size, QFont.Weight.Bold if bold else QFont.Weight.Normal))
    return item


def box(parent, x, y, w, h, color=PANEL, border=LINE):
    item = QFrame(parent)
    item.setGeometry(x, y, w, h)
    item.setStyleSheet(f"background:{color}; border:1px solid {border}; border-radius:12px;")
    return item


def button(parent, x, y, w, text, *, primary=False, disabled=False):
    item = QPushButton(text, parent)
    item.setGeometry(x, y, w, 40)
    item.setFont(QFont("DejaVu Sans", 11, QFont.Weight.Bold))
    item.setStyleSheet(
        f"background:{ACCENT if primary else PANEL}; color:{BG if primary else INK};"
        f"border:1px solid {ACCENT if primary else LINE}; border-radius:8px;"
    )
    if disabled:
        item.setEnabled(False)
        item.setStyleSheet(f"background:{PANEL}; color:#738296; border:1px solid {LINE}; border-radius:8px;")
    return item


def render(app, state):
    window = QWidget()
    window.setFixedSize(1120, 780)
    window.setStyleSheet(f"background:{BG};")
    empty = state == "empty"
    pattern = state == "pattern"
    conflict = state == "conflict"
    unknown = state == "unknown-price"
    box(window, 0, 0, 1120, 62, "#111b2a", "#111b2a")
    label(window, 24, 12, 170, 36, "VIBIX  Studio", 14, bold=True)
    label(window, 200, 12, 430, 36, "Набор · Рождественский сад", 13)
    button(window, 817, 11, 117, "Все проекты")
    button(window, 948, 11, 148, "Настройки API")
    label(window, 24, 72, 1050, 24, "МАКЕТ ДЛЯ СОГЛАСОВАНИЯ · 1120 × 780 · данные и цены демонстрационные", 10, MUTED)
    label(window, 24, 111, 710, 34, "Проверьте набор перед запуском", 23, bold=True)
    label(window, 24, 153, 900, 26, "1  Идея и стиль     →     2  Элементы и промпты     →     3  Проверка и запуск", 12, ACCENT)

    left = box(window, 24, 198, 638, 470)
    label(left, 20, 15, 440, 32, "Элементы набора", 16, bold=True)
    label(left, 20, 50, 590, 36, "Назначение задаёт обработку. Можно менять у каждого элемента.", 11, MUTED)
    if empty:
        label(left, 34, 120, 550, 58, "В наборе пока нет элементов", 19, bold=True)
        label(left, 34, 188, 540, 68, "Добавьте предметы или выберите пресет в конструкторе.\nГенерация не начнётся автоматически.", 13, MUTED)
        button(left, 34, 280, 250, "Перейти к конструктору")
    else:
        label(left, 22, 95, 275, 26, "НАЗВАНИЕ", 10, MUTED)
        label(left, 310, 95, 180, 26, "НАЗНАЧЕНИЕ", 10, MUTED)
        label(left, 506, 95, 115, 26, "МОДЕЛЬ", 10, MUTED)
        rows = [("01", "Пуансеттия", "Клипарт"), ("02", "Еловая ветка", "Клипарт"), ("03", "Цветочный узор", "Паттерн")]
        selected = 2 if pattern else 0
        for i, (number, name, kind) in enumerate(rows):
            y = 133 + i * 68
            row = box(left, 12, y, 614, 57, "#153b40" if i == selected else "#182232", ACCENT if i == selected else LINE)
            label(row, 10, 10, 33, 36, number, 11, MUTED)
            label(row, 48, 10, 242, 36, name, 12, bold=i == selected)
            button(row, 293, 8, 160, kind + "  ▾")
            label(row, 469, 9, 138, 37, "GPT Image 2", 10)
        label(left, 20, 348, 588, 45, "3 изображения · 2 клипарта + 1 плитка\nСуществующие файлы остаются в проекте.", 11, MUTED)
        button(left, 20, 411, 223, "Изменить промпт")
        label(left, 266, 410, 350, 42, "Модель выбирается для генерации;\nобработка определяется назначением.", 10, MUTED)

    right = box(window, 680, 198, 416, 470)
    label(right, 20, 15, 376, 32, "Обработка элемента", 16, bold=True)
    label(right, 20, 55, 376, 33, "Выберите элемент слева" if empty else "03 · Цветочный узор" if pattern else "01 · Пуансеттия", 13, ACCENT)
    if empty:
        label(right, 20, 113, 368, 105, "Здесь появятся цвет фона, этапы обработки и формат результата выбранного элемента.", 14, MUTED)
    else:
        label(right, 20, 100, 373, 25, "ПАЛИТРА ПРЕДМЕТА", 10, MUTED)
        for i, color in enumerate(["#ae3949", "#d9888e", "#efdfbb", "#386554", "#193d35"]):
            box(right, 20 + i * 42, 137, 32, 25, color, color)
        label(right, 241, 128, 159, 41, "Изменить в стиле", 10, MUTED)
        if pattern:
            title, body = "Фон сохраняется", "Цвет бумаги является частью узора.\nУдаление фона и обрезка отключены."
        elif conflict:
            title, body = "Конфликт фона", "В промпте указан белый фон,\nа для обработки выбран синий."
        else:
            title, body = "Chroma-фон · Авто · синий", "Выбран с учётом палитры и описания.\nПосле генерации проверим реальный фон."
        panel = box(right, 16, 183, 384, 104, "#342c23" if conflict else "#15343b", "#c99b59" if conflict else "#297978")
        label(panel, 12, 7, 356, 32, title, 12, "#f0c38a" if conflict else INK, True)
        label(panel, 12, 41, 356, 53, body, 10, MUTED)
        stages = ["1  Генерация плитки", "2  Проверка повторения и швов", "3  Экспорт PNG без обрезки"] if pattern else ["1  Генерация изображения", "2  Проверка и удаление фона", "3  Проверка края и экспорт PNG"]
        for i, text in enumerate(stages):
            label(right, 20, 303 + i * 35, 375, 29, text, 11)
        label(right, 20, 415, 373, 44,
              "Проверка швов не гарантирована словом seamless." if pattern else "Если PNG уже содержит alpha, сохраняем её\nи проверяем вместо повторного удаления фона.", 10, MUTED)

    note = "Добавьте элементы, чтобы рассчитать запуск." if empty else "Оценка недоступна. Обновите её перед запуском." if unknown else "Исправьте конфликт в промпте. Запуск набора заблокирован." if conflict else "Пример оценки: $0.09 за 3 изображения · локальное удаление фона $0"
    label(window, 24, 682, 1072, 30, note, 12, "#f0c38a" if (conflict or unknown) else INK)
    label(window, 24, 722, 650, 37, "Результаты проходят проверку. Сомнительные файлы требуют просмотра.", 10, MUTED)
    button(window, 696, 722, 167, "Назад к набору")
    button(window, 878, 722, 218,
           "Исправить промпт" if conflict else "Обновить оценку" if unknown else "Создать изображения" if empty else "Создать 3 изображения",
           primary=True, disabled=empty)
    if state == "type-menu":
        menu = box(window, 329, 382, 260, 214, "#293749", "#668087")
        for i, text in enumerate(("Клипарт  ✓", "Паттерн", "Фон", "Текстура")):
            label(menu, 16, 10 + i * 37, 225, 32, text, 12, ACCENT if i == 0 else INK)
        label(menu, 16, 159, 228, 43, "Страницы журнала: отдельный\nбудущий модуль", 10, MUTED)
    window.show()
    app.processEvents()
    assert window.size().width() == 1120 and window.size().height() == 780
    assert window.grab().save(str(OUT / f"{state}-1120x780.png"))
    window.close()


def main():
    with tempfile.TemporaryDirectory(prefix="vibix-mockup-") as temporary:
        os.environ["LOCALAPPDATA"] = temporary
        app = QApplication.instance() or QApplication([])
        for state in ("clipart", "pattern", "empty", "conflict", "unknown-price", "type-menu"):
            render(app, state)
        # Capture the current real page for comparison, using safe defaults only.
        from v3_project_state import ProjectState, ProjectMode, PromptEntry
        from v3_clipart_flow import ClipartReviewRunPage
        from v3_components import apply_v3_theme
        state = ProjectState(mode=ProjectMode.CLIPART)
        state.common.work_dir = temporary
        state.clipart.prompts = [PromptEntry("Poinsettia clipart"), PromptEntry("Fir branch clipart")]
        page = ClipartReviewRunPage(state)
        apply_v3_theme(page)
        page.resize(1120, 780)
        page.show()
        app.processEvents()
        assert page.grab().save(str(OUT / "current-review-1120x780.png"))
        page.close()
    print("Rendered six proposal states and current real review page; no network calls.")


if __name__ == "__main__":
    main()
