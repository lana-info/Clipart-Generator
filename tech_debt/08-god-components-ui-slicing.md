# P1 — разрезать god-components без изменения UX

Status: Done (2026-08-17)

Dependency map for this slice: `MainWindow.setup_ui` owns the process-grid
composition; `VisibleMarkSettingsWidget` owns the mode combo, confirmation
label, object names and enabled/visibility state; `MainWindow` retains only
legacy aliases and persistence wiring. Independent review scored the first
pass 5/10; one corrective pass restored size policy, autonomous initial state
and offscreen widget contract tests. Full Qt tests remain environment-blocked
locally because `PyQt6` is not installed.

## Проблема и evidence

- `MainWindow` начинается примерно на строке 3570, содержит около 3.1k строк и
  114 методов; `setup_ui` — около 800 строк.
- В нём смешаны legacy UI, config, API settings, license gate, updater,
  processing controls и runtime callbacks.
- V3 modules уже существуют (`v3_mode_selection`, `v3_clipart_flow`,
  `v3_processing_flow`), поэтому часть нового UI обходится legacy shell.

## Цель

Снизить coupling небольшими вертикальными slices, оставляя прежний UX и
совместимые test seams.

## Минимальная реализация

1. Снять dependency map и ownership каждого widget group.
2. Первыми вынести автономные dialogs/widgets: visible-mark selector, prompt
   import/reference dialogs, provider settings cards.
3. Затем вынести updater/license/network UI adapters после 09.
4. `MainWindow` оставить composition root, а не переносить все `self.*` в
   механический файл.

## TDD и acceptance

- Widget construction offscreen tests проверяют object names, signal wiring,
  enabled/disabled states и save/load.
- Dialog tests проверяют cancel/accept и malformed input.
- Three mode flows, startup license gate и old config smoke remain green.
- Deletion test: после extraction исходный класс не содержит доменную логику
  вынесенного feature.

## Подводные камни

- Не извлекать `setup_ui` целиком — получится shallow module с тем же coupling.
- Не менять layout/labels без acceptance evidence.
- Не смешивать extraction с новыми UX features.
