"""Small, provider-independent locale contract for the v3 UI.

The application locale is intentionally separate from prompt language, model
identifiers and internal status values. Full UI translation can build on this
contract without changing persisted project data.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


DEFAULT_LOCALE = "ru"
SUPPORTED_LOCALES = ("ru", "en")


_MESSAGES = {
    "ru": {
        "pinterest.product_input_title": "Фотография товара",
        "pinterest.product_input_description": "Добавьте фотографию товара для защищённого слоя.",
        "pinterest.copy_layout_title": "Текст и оформление пина",
        "pinterest.copy_layout_description": "Задайте заголовок, призыв и описание оформления для серии.",
        "pinterest.products": "Фотографии товара",
        "pinterest.add_products": "Добавить фотографии",
        "pinterest.selected_product": "Товар для серии",
        "pinterest.title": "Заголовок",
        "pinterest.subtitle": "Подзаголовок",
        "pinterest.cta": "Призыв к действию",
        "pinterest.style": "Стиль",
        "pinterest.scene": "Описание сцены",
        "pinterest.palette": "Палитра",
        "pinterest.output_folder": "Папка результата",
        "pinterest.choose": "Выбрать",
        "pinterest.suggest_copy": "Подставить введённый текст",
        "pinterest.no_products": "Фотографии товара не выбраны.",
        "pinterest.preview_title": "Предпросмотр Pinterest-пинов",
        "pinterest.preview_description": "Шесть фиксированных слотов: три шаблона и три AI-сцены.",
        "pinterest.export": "Экспортировать принятые",
        "pinterest.accept": "Принять вариант",
        "pinterest.regenerate": "Перегенерировать",
        "pinterest.source": "Источник",
        "pinterest.variant": "Вариант",
        "pinterest.fidelity_warning": "Предупреждение: точность товара не подтверждена защищённым слоем.",
        "pinterest.export_ready": "К экспорту выбрано: {count}",
        "pinterest.export_summary": "Сохранено: {count}; папка: {folder}",
        "pinterest.status.partial_export": "Сохранено не все выбранные варианты: {count}.",
        "pinterest.status.safe_template_fallback": "AI-сцена недоступна у выбранного провайдера; использованы безопасные шаблоны.",
        "pinterest.regeneration_another_run_active": "Сначала завершите текущее задание в другом режиме",
        "pinterest.regeneration_already_running": "Запуск уже выполняется",
        "pinterest.regeneration_started": "Перегенерируется выбранный Pinterest-вариант",
        "pinterest.status_pending": "Ожидает генерации",
        "pinterest.status_success": "Готов",
        "pinterest.status_failed": "Не удалось создать",
        "pinterest.image_unavailable": "Предпросмотр изображения недоступен",
        "pinterest.format_title": "Генерация Pinterest-пинов",
        "pinterest.format_accessible": "Генерация Pinterest-пинов с защищённым товаром",
        "pinterest.format_recommendation": "Фиксированный формат — 2:3, 1000×1500 px. Товар остаётся отдельным защищённым слоем.",
        "pinterest.generation_description": "Выберите модель и формат для защищённой серии Pinterest-пинов.",
        "pinterest.generation_model": "Модель",
        "pinterest.generation_ratio": "Пропорция",
        "pinterest.generation_resolution": "Разрешение",
        "pinterest.generation_variants": "Вариантов на пин",
        "pinterest.generation_scope": "Настройки применяются ко всей серии Pinterest-пинов.",
        "pinterest.review_description": "Проверьте готовность шести слотов перед явным запуском.",
        "pinterest.review_title": "Генерация",
        "pinterest.status.reference_ready": "Reference-режим готов: выбранная модель и формат совместимы.",
        "pinterest.status.preflight_ready": "Пакет готов к генерации после нажатия «Запустить».",
        "pinterest.status.run_started": "Запущена защищённая серия Pinterest-пинов",
        "pinterest.error.runtime_settings": "Настройки запуска повреждены",
        "pinterest.error.authorization_unavailable": "Лицензионный сервис не настроен",
        "pinterest.error.pin_prepare_failed": "Не удалось подготовить Pinterest-пины.",
        "pinterest.status.run_finished": "Серия Pinterest-пинов завершена",
        "pinterest.status.run_cancelled": "Генерация Pinterest-пинов отменена",
        "pinterest.error.pin_export_failed": "Не удалось экспортировать Pinterest-пин.",
        "pinterest.error.reference_incompatible": "Для выбранной модели и формата нет совместимой reference-модели.",
        "pinterest.error.missing_product": "Добавьте фотографию товара",
        "pinterest.error.product_unavailable": "Фотография товара недоступна",
        "pinterest.error.output_folder": "Папка результата недоступна для записи",
        "pinterest.error.scene_failed": "Не удалось создать AI-сцену. Можно повторить только этот вариант.",
        "pinterest.error.run_wrong_mode": "Запуск Pinterest-пинов доступен только в режиме Pinterest",
        "pinterest.error.work_folder": "Рабочая папка не существует или недоступна для записи",
    },
    "en": {
        "pinterest.product_input_title": "Product photo",
        "pinterest.product_input_description": "Add a product photo for the protected source layer.",
        "pinterest.copy_layout_title": "Pin copy and layout",
        "pinterest.copy_layout_description": "Set the title, call to action, and layout description for the series.",
        "pinterest.products": "Product photos",
        "pinterest.add_products": "Add photos",
        "pinterest.selected_product": "Product for this series",
        "pinterest.title": "Title",
        "pinterest.subtitle": "Subtitle",
        "pinterest.cta": "Call to action",
        "pinterest.style": "Style",
        "pinterest.scene": "Scene description",
        "pinterest.palette": "Palette",
        "pinterest.output_folder": "Output folder",
        "pinterest.choose": "Choose",
        "pinterest.suggest_copy": "Use entered copy",
        "pinterest.no_products": "No product photos selected.",
        "pinterest.preview_title": "Pinterest pin preview",
        "pinterest.preview_description": "Six fixed slots: three templates and three AI scenes.",
        "pinterest.export": "Export accepted",
        "pinterest.accept": "Accept variant",
        "pinterest.regenerate": "Regenerate",
        "pinterest.source": "Source",
        "pinterest.variant": "Variant",
        "pinterest.fidelity_warning": "Warning: product fidelity is not confirmed by a protected layer.",
        "pinterest.export_ready": "Ready to export: {count}",
        "pinterest.export_summary": "Saved: {count}; folder: {folder}",
        "pinterest.status.partial_export": "Only part of the selected variants was saved: {count}.",
        "pinterest.status.safe_template_fallback": "AI scenes are unavailable for the selected provider; safe templates were used.",
        "pinterest.regeneration_another_run_active": "Finish the current task in the other mode first.",
        "pinterest.regeneration_already_running": "Generation is already running.",
        "pinterest.regeneration_started": "Regenerating selected Pinterest variant.",
        "pinterest.status_pending": "Waiting for generation",
        "pinterest.status_success": "Ready",
        "pinterest.status_failed": "Could not generate",
        "pinterest.image_unavailable": "Image preview is unavailable",
        "pinterest.format_title": "Pinterest pin generation",
        "pinterest.format_accessible": "Pinterest pin generation with protected product",
        "pinterest.format_recommendation": "The format is fixed at 2:3, 1000×1500 px. The product remains a separate protected layer.",
        "pinterest.generation_description": "Choose the model and format for the protected Pinterest pin series.",
        "pinterest.generation_model": "Model",
        "pinterest.generation_ratio": "Aspect ratio",
        "pinterest.generation_resolution": "Resolution",
        "pinterest.generation_variants": "Variants per pin",
        "pinterest.generation_scope": "These settings apply to the complete Pinterest pin series.",
        "pinterest.review_description": "Check the six slots before explicitly starting generation.",
        "pinterest.review_title": "Generation",
        "pinterest.status.reference_ready": "Reference mode is ready: the selected model and format are compatible.",
        "pinterest.status.preflight_ready": "The package is ready to generate after you select Start.",
        "pinterest.status.run_started": "Protected Pinterest pin series started.",
        "pinterest.error.runtime_settings": "Run settings are invalid.",
        "pinterest.error.authorization_unavailable": "The licensing service is not configured.",
        "pinterest.error.pin_prepare_failed": "Pinterest pins could not be prepared.",
        "pinterest.status.run_finished": "Pinterest pin series completed.",
        "pinterest.status.run_cancelled": "Pinterest pin generation was cancelled.",
        "pinterest.error.pin_export_failed": "Pinterest pin export failed.",
        "pinterest.error.reference_incompatible": "No compatible reference model is available for the selected model and format.",
        "pinterest.error.missing_product": "Add a product photo",
        "pinterest.error.product_unavailable": "The product photo is unavailable",
        "pinterest.error.output_folder": "The output folder is unavailable for writing",
        "pinterest.error.scene_failed": "The AI scene could not be created. You can retry only this variant.",
        "pinterest.error.run_wrong_mode": "Pinterest pins can only run in Pinterest mode",
        "pinterest.error.work_folder": "The work folder does not exist or is unavailable for writing",
    },
}


def normalize_locale(value: Any, *, default: str = DEFAULT_LOCALE) -> str:
    """Return a supported base language for a user or OS language tag."""

    fallback = str(default or DEFAULT_LOCALE).strip().casefold().split("-", 1)[0]
    if fallback not in SUPPORTED_LOCALES:
        fallback = DEFAULT_LOCALE
    raw = str(value or "").strip().replace("_", "-").casefold()
    base = raw.split("-", 1)[0]
    return base if base in SUPPORTED_LOCALES else fallback


def message_for(key: str, *, locale: Any = DEFAULT_LOCALE, **values: Any) -> str:
    """Return a localized visible message from the shared registry."""

    try:
        template = _MESSAGES[normalize_locale(locale)][key]
    except KeyError as error:
        raise KeyError(f"Unknown localized message: {key!r}") from error
    return template.format(**values)


def app_locale_from_settings(settings: Mapping[str, Any] | None) -> str:
    """Read only the UI locale setting, preserving prompt-language semantics."""

    source = settings if isinstance(settings, Mapping) else {}
    return normalize_locale(source.get("app_language"))


def with_app_locale(
    settings: Mapping[str, Any] | None,
    locale: Any,
) -> dict[str, Any]:
    """Return settings with a normalized UI locale, without mutating input."""

    result = dict(settings) if isinstance(settings, Mapping) else {}
    result["app_language"] = normalize_locale(locale)
    return result


__all__ = [
    "DEFAULT_LOCALE",
    "SUPPORTED_LOCALES",
    "app_locale_from_settings",
    "normalize_locale",
    "message_for",
    "with_app_locale",
]
