# P1 — единый каталог моделей и провайдеров

Status: Done (2026-08-17)

Evidence: `model_catalog.py`, `tests/test_model_catalog.py`, strict endpoint
lookup and compatibility exports in `main.py`/`v3_clipart_flow.py`. The
independent review scored the first pass 4/10; one corrective pass closed the
strict-lookup and mutable-compatibility findings. Full UI tests remain
environment-blocked because `PyQt6` and `Pillow` are not installed.

## Проблема и evidence

- `main.py` содержит `MODEL_CAPABILITIES`, `GENERATION_MODELS`, supported/visible
  ids и routing helpers.
- `v3_clipart_flow.py` содержит `_legacy_catalog`, `_legacy_model_capabilities`
  и собственные option/price derivation.
- Processing provider options находятся в `v3_provider_registry.py`, а runtime
  validation частично остаётся в legacy worker.

## Цель

Один immutable catalog обслуживает UI options, capability validation, pricing,
reference routing и payload endpoint mapping.

## Минимальная реализация

1. Сначала зафиксировать текущие catalog outputs snapshot/contract tests.
2. Вынести только data и pure lookup functions; UI labels и network calls не
   смешивать с catalog.
3. Оставить compatibility re-export из `main`/`v3_clipart_flow` на миграцию.
4. Проверять неизвестную модель явной ошибкой, а не молчаливым fallback.

## TDD и acceptance

- Для каждой видимой модели сохраняются id, type, ratios/resolutions/quality,
  pricing и reference compatibility.
- GPT Image 2 с reference и без reference сохраняет разные endpoint ids.
- UI, preflight и worker получают одинаковый result для одной model id.
- Provider key requirement определяется выбранным provider, без ложного KIE gate.

## Подводные камни

- Не удалять модели только потому, что они не видимы в UI.
- Не превращать цены в источник биллинга: это estimate/UX information.
- Не менять порядок или текст UI без продуктовой причины.
