import os
import unittest


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPalette
from PyQt6.QtWidgets import QApplication, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from v3_components import (
    DEFAULT_TOKENS,
    AdvancedSection,
    ButtonVariant,
    CardState,
    FormCard,
    ModeCard,
    V3Button,
    V3DesignTokens,
    apply_v3_theme,
    build_v3_stylesheet,
)


def _contrast_ratio(foreground: str, background: str) -> float:
    def channel(value: int) -> float:
        value /= 255
        return value / 12.92 if value <= 0.03928 else ((value + 0.055) / 1.055) ** 2.4

    def luminance(value: str) -> float:
        value = value.lstrip("#")
        return 0.2126 * channel(int(value[0:2], 16)) + 0.7152 * channel(int(value[2:4], 16)) + 0.0722 * channel(int(value[4:6], 16))

    light, dark = sorted((luminance(foreground), luminance(background)), reverse=True)
    return (light + 0.05) / (dark + 0.05)


class V3ComponentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def tearDown(self):
        self.app.processEvents()

    def test_tokens_generate_shared_focus_disabled_and_state_styles(self):
        stylesheet = build_v3_stylesheet()
        self.assertIn(DEFAULT_TOKENS.canvas, stylesheet)
        self.assertIn(DEFAULT_TOKENS.accent, stylesheet)
        self.assertIn(DEFAULT_TOKENS.focus, stylesheet)
        self.assertIn(':focus', stylesheet)
        self.assertIn(':disabled', stylesheet)
        self.assertIn('border: 2px dashed', stylesheet)
        self.assertIn('QToolButton[v3Disclosure="true"]:disabled', stylesheet)
        self.assertIn('[state="warning"]', stylesheet)
        self.assertIn('[state="error"]', stylesheet)

    def test_button_variants_are_accessible_and_focusable(self):
        button = V3Button("Продолжить", ButtonVariant.SECONDARY)
        self.assertEqual(button.variant, ButtonVariant.SECONDARY)
        self.assertEqual(button.focusPolicy(), Qt.FocusPolicy.StrongFocus)
        self.assertEqual(button.accessibleName(), "Продолжить")

        button.set_variant(ButtonVariant.DESTRUCTIVE)
        self.assertEqual(button.variant, ButtonVariant.DESTRUCTIVE)
        self.assertEqual(button.accessibleDescription(), "Опасное действие")
        button.setEnabled(False)
        self.assertFalse(button.isEnabled())
        button.deleteLater()

    def test_form_card_uses_text_markers_for_warning_and_error(self):
        card = FormCard("Параметры", "Настройте результат")
        card.add_widget(QLabel("Поле"))

        card.set_state(CardState.WARNING, "стоимость не рассчитана")
        self.assertEqual(card.state, CardState.WARNING)
        self.assertTrue(card.status_label.text().startswith("⚠ Предупреждение:"))
        self.assertFalse(card.status_label.isHidden())

        card.set_state(CardState.ERROR, "папка не выбрана")
        self.assertEqual(card.state, CardState.ERROR)
        self.assertTrue(card.status_label.text().startswith("✕ Ошибка:"))
        self.assertIn("папка не выбрана", card.accessibleDescription())

        card.set_state(CardState.DEFAULT)
        self.assertTrue(card.status_label.isHidden())
        card.deleteLater()

    def test_mode_card_emits_mode_and_shows_non_color_selection_marker(self):
        card = ModeCard(
            "clipart",
            "Создать клипарт",
            "Серия изолированных объектов",
            "набор PNG",
        )
        selected = []
        card.selected.connect(selected.append)
        card.start_button.click()
        self.assertEqual(selected, ["clipart"])

        card.set_selected(True)
        self.assertTrue(card.is_selected)
        self.assertFalse(card.selection_label.isHidden())
        self.assertTrue(card.selection_label.text().startswith("✓"))
        self.assertIn("Выбран режим", card.accessibleDescription())
        card.deleteLater()

    def test_mode_card_accepts_optional_illustration(self):
        card = ModeCard(
            "clipart",
            "Создать клипарт",
            "Серия изолированных объектов",
            "набор PNG",
            illustration_path="assets/mode-clipart.svg",
        )
        self.assertIsNotNone(card.illustration)
        self.assertEqual(card.illustration.accessibleName(), "Иллюстрация режима: Создать клипарт")
        card.deleteLater()

    def test_mode_card_renders_png_illustration_with_a_loaded_pixmap(self):
        card = ModeCard(
            "clipart",
            "Создать клипарт",
            "Серия изолированных объектов",
            "набор PNG",
            illustration_path="website/vibix-download/assets/mode-clipart-hq.png",
        )
        self.assertIsInstance(card.illustration, QLabel)
        self.assertIsNotNone(card.illustration.pixmap())
        self.assertFalse(card.illustration.pixmap().isNull())
        self.assertEqual(
            card.illustration.accessibleName(),
            "Иллюстрация режима: Создать клипарт",
        )
        card.deleteLater()

    def test_advanced_section_is_collapsed_by_default_and_keyboard_focusable(self):
        section = AdvancedSection()
        section.add_widget(QLabel("Редкая настройка"))
        changes = []
        section.expanded_changed.connect(changes.append)

        self.assertFalse(section.is_expanded)
        self.assertTrue(section.content.isHidden())
        self.assertEqual(
            section.toggle_button.focusPolicy(),
            Qt.FocusPolicy.StrongFocus,
        )
        section.setDisabled(True)
        self.assertFalse(section.toggle_button.isEnabled())
        section.setEnabled(True)

        section.set_expanded(True)
        self.assertTrue(section.is_expanded)
        self.assertFalse(section.content.isHidden())
        self.assertEqual(changes, [True])
        self.assertEqual(
            section.toggle_button.accessibleDescription(),
            "Раздел раскрыт",
        )

        section.toggle_button.click()
        self.assertFalse(section.is_expanded)
        self.assertTrue(section.content.isHidden())
        self.assertEqual(changes, [True, False])
        section.deleteLater()

    def test_components_honor_custom_spacing_tokens(self):
        tokens = V3DesignTokens(space_2=6, space_3=10, space_4=20)
        form = FormCard("Параметры", tokens=tokens)
        mode = ModeCard("clipart", "Клипарт", "Описание", "PNG", tokens=tokens)
        advanced = AdvancedSection(tokens=tokens)

        self.assertEqual(form.layout().contentsMargins().left(), 20)
        self.assertEqual(form.content_layout.spacing(), 10)
        self.assertEqual(mode.layout().contentsMargins().left(), 20)
        self.assertEqual(advanced.layout().spacing(), 6)

        form.deleteLater()
        mode.deleteLater()
        advanced.deleteLater()

    def test_component_smoke_at_minimum_window_size(self):
        root = QWidget()
        root.resize(980, 700)
        apply_v3_theme(root)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(
            DEFAULT_TOKENS.space_6,
            DEFAULT_TOKENS.space_6,
            DEFAULT_TOKENS.space_6,
            DEFAULT_TOKENS.space_6,
        )
        layout.setSpacing(DEFAULT_TOKENS.space_4)

        cards = QWidget()
        cards_layout = QHBoxLayout(cards)
        cards_layout.setContentsMargins(0, 0, 0, 0)
        cards_layout.setSpacing(DEFAULT_TOKENS.space_4)
        for mode_id, title in (
            ("clipart", "Создать клипарт"),
            ("pinterest", "Создать Pinterest-пины"),
            ("processing", "Обработать изображения"),
        ):
            cards_layout.addWidget(
                ModeCard(
                    mode_id,
                    title,
                    "Короткое описание рабочего сценария",
                    "готовые изображения",
                )
            )
        layout.addWidget(cards)

        form = FormCard("Проверка", "Компоненты помещаются в минимальное окно")
        advanced = AdvancedSection()
        advanced.add_widget(QLabel("Дополнительная настройка"))
        form.add_widget(advanced)
        layout.addWidget(form)

        root.show()
        self.app.processEvents()

        self.assertEqual(root.size().width(), 980)
        self.assertEqual(root.size().height(), 700)
        self.assertGreater(cards.width(), 0)
        self.assertLessEqual(cards.geometry().right(), root.contentsRect().right())
        self.assertLessEqual(form.geometry().right(), root.contentsRect().right())
        self.assertLessEqual(form.geometry().bottom(), root.contentsRect().bottom())
        self.assertTrue(root.styleSheet())

        root.close()
        root.deleteLater()

    def test_theme_applies_global_dark_palette_and_contrast(self):
        root = QWidget()
        apply_v3_theme(root)
        palette = self.app.palette()
        self.assertEqual(palette.color(QPalette.ColorRole.Window).name(), DEFAULT_TOKENS.canvas)
        self.assertEqual(palette.color(QPalette.ColorRole.Text).name(), DEFAULT_TOKENS.text)
        self.assertGreaterEqual(
            _contrast_ratio(DEFAULT_TOKENS.text, DEFAULT_TOKENS.canvas), 7.0
        )
        root.deleteLater()


if __name__ == "__main__":
    unittest.main()
