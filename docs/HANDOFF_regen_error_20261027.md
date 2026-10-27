# Поиск бага: ошибка при перегенерации и обработке (Auto Clipart), 2026-10-27

> Статус 2026-10-27: причина найдена и исправлена в ветке `fix/regen-processing-error-journal` — см. `docs/ERRORS.md` {#regen-restored-session-journal-20261027}. Документ устарел, оставлен как след поиска.

Рабочий каталог: `ui-release-polish-20261024-worktree`, ветка `fix/regen-blocked-journal-buttons` (от develop/3.2, версия 3.2.45). Русский язык ответов; правила проекта — `AGENTS.md`, ошибки пишутся только в `docs/ERRORS.md`.

## Симптом (владелец, Windows 11, Studio 3.2.45)
- Шаг «Результаты», выбрано «Пересоздать помеченные (11)»: брак генерации 10, брак вырезания 1. Перегенерация не даёт новой картинки.
- На экране у файла: «Файл не обработан. Не удалось завершить обработку файла.» (универсальная заглушка `_failure_reason` в `v3_run_queue.py`, ветка `processing_error`; настоящий текст ошибки в интерфейс не попадает).
- Диагностика, присланная сразу после ошибки: ни одного события запуска (нет run_started, item_failed, regenerate_started) — только запуск программы, обновление, workflow_step_changed. Нумерация событий сплошная, то есть события не создавались, а не терялись при записи или экспорте. По словам владельца, журнал не писал запуски и в предыдущих версиях.

## Что уже проверено
- На Linux журнал работает: `WorkflowHost` → `shell.diagnostic_journal` → `RunQueueSession._event` пишет события (проверено скриптом с реальными `AppShell`, `WorkflowHost`, `DiagnosticJournal`).
- Модульный пакет auto-clipart не содержит `v3_run_queue` и `diagnostics`; они из ядра (`studio_module_packaging.py`, `OFFICIAL_WORKFLOW_FILES`).
- Тесты 698 проходят (`-k "run_queue or clipart or review or results or diagnos"`).

## Гипотезы
1. Перегенерация отказывает ДО запуска (молча): `RunQueueSupport.regenerate_selected` → подтверждение, `_keep_previous_outputs` (`before_replace_outputs`/`keep_version`: `MAX_VERSIONS = 10`, `_within`, symlink-проверки на Windows), `create_worker_for_request`. Ошибка тогда уходит в `controller._error` → `handle_fatal_error` (раньше выходил молча, если запуск уже завершён). Теперь эти отказы пишутся как `regenerate_blocked` с причиной (коммит 7c1cd4f).
2. В 3.2.45 перегенерация гонит полную цепочку (хромакей + увеличение после), UP-10 (`_ensure_delivery_operations` в `studio_auto_clipart_flow.py`); этап может падать с текстом, не попавшим под классификацию.
3. Реальный дефект записи журнала на Windows в запущенном приложении (в тестах не воспроизводится): сравнить, что реально приходит в `RunQueueSession._diagnostic_journal` у собранного приложения (замороженная сборка, модуль из подписанного пакета).

## Что нужно
1. Найти причину, по которой запуск (в том числе обычная генерация) не оставляет событий в журнале у владельца, или доказать, что запусков в этих сессиях не было.
2. Найти причину ошибки перегенерации/обработки и исправить с регрессионным тестом.
3. Показывать пользователю не заглушку, а понятную причину.
4. Записать причину, неверные попытки, решение и проверку в `docs/ERRORS.md`; статус — в `TASKS.md` (UP-14).

## Файлы
`v3_run_queue.py` (RunQueueSession, RunQueueSupport.regenerate_selected, _failure_reason, handle_fatal_error), `studio_auto_clipart_flow.py` (confirm_retry_request, _ensure_delivery_operations), `studio_clipart_review_ui.py` (recreate_marked, before_replace_outputs), `studio_clipart_versions.py`, `studio_workflow_host.py`, `_studio_workflow_core.py`, `diagnostics.py`, `v3_mode_selection.py` (shell.diagnostic_journal).
