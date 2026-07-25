# Архитектурный обзор перед реализацией 3.0

Дата: 2026-07-25

Статус: read-only review, рабочий код не изменён

## Наблюдаемое состояние

- `main.py`: 6385 строк, около 298 KB.
- `WorkerThread`: строки 569–2876, 2308 строк, 108 методов.
- `MainWindow`: строки 3383–6375, 2993 строки, 108 методов.
- `MainWindow.setup_ui`: 795 строк.
- 44 метода `WorkerThread` и 19 методов `MainWindow` прямо используются или
  подменяются тестами.
- `CONTEXT.md` и `docs/adr/` в проекте отсутствуют; для доменных названий
  использованы термины из `PRD_3.0.ru.md`.

Главная проблема — низкая Locality: правила проекта, конфигурация, Qt widgets,
сетевые запросы, provider routing, orchestration и файловая публикация находятся
в двух очень больших Module. При этом прямой перенос методов по одному создаст
shallow Module и увеличит Interface вместо появления Depth.

## Кандидат 1: UI выбора области видимой метки

Files:
- `main.py`: `ImageRegionSelector`, строки 3210–3299.
- `main.py`: `VisibleMarkRegionDialog`, строки 3302–3380.

Problem:
Автономная геометрия и отрисовка находятся между prompt-диалогами и
`MainWindow`, хотя окно использует готовый результат выбора.

Solution:
Перенести связный Module выбора области целиком, сохранив вызов из
`MainWindow`.

Benefits:
Deletion test проходит: при удалении Module вся геометрия и Qt painting
вернутся в `MainWindow`. Перенос даёт Locality и небольшой Interface.

Risk and tests:
- Риск низкий.
- Есть косвенное покрытие в `test_visible_mark_pipeline.py` и
  `test_visible_mark_ui.py`.
- Перед переносом полезны узкие тесты масштабирования координат.

## Кандидат 2: prompt-таблица и диалоги импорта

Files:
- `main.py`: `PromptTableWidget`, строки 2879–2889.
- `main.py`: `CsvImportDialog`, строки 2892–3083.
- `main.py`: `PromptReferencesDialog`, строки 3086–3207.

Problem:
Готовые UI Module для prompt workflow не являются частью реализации главного
окна, но физически увеличивают `main.py`.

Solution:
Перенести эти три связных Module вместе с CSV parsing и правилами reference
limit. Не дробить каждый маленький widget в отдельный файл.

Benefits:
Deletion test проходит: без них CSV parsing, reference normalization и
диалоговое состояние вернутся в `MainWindow`. Это увеличивает Depth и сохраняет
Locality prompt workflow.

Risk and tests:
- Риск низкий.
- Контракты CSV и reference limits покрыты
  `test_trustworthy_feature_contracts.py`.

## Кандидат 3: каталог моделей и правила совместимости

Files:
- `main.py`: model constants и metadata, строки 113–208 и 384–450.
- `main.py`: `get_model_capabilities`, строки 365–373.
- `main.py`: `resolve_kie_generation_model`, строки 376–381.
- Связанные дублирующие правила находятся в `WorkerThread` и `MainWindow`.

Problem:
Один доменный факт о модели сейчас интерпретируют worker и UI. Из-за этого
изменение модели требует синхронного редактирования нескольких мест.

Solution:
Собрать каталог и чистые правила выбора в один глубокий Module. На первом шаге
сохранить совместимые импорты из `main`, чтобы существующие тестовые seams не
сломались.

Benefits:
Высокий Leverage: один набор правил обслуживает UI, preflight и generation.
Locality снижает риск расхождения payload и доступных контролов.

Risk and tests:
- Риск низкий–средний из-за существующих дублирующих Adapter-методов.
- Покрытие: `test_kie_routing.py`, `test_main_ui_acceptance.py`,
  `test_trustworthy_feature_contracts.py`.

## Кандидат 4: схема конфигурации и миграция

Files:
- `main.py`: `load_config`, строки 3477–3596.
- `main.py`: legacy migration и сохранение конфигурации, около 3598–3613.
- `main.py`: autosave wiring, строки 4635–4694.
- `main.py`: `persist_ui_settings`, строки 6283–6366.

Problem:
Defaults, legacy migration, нормализация и чтение Qt widgets смешаны. Новый
wizard иначе будет вынужден копировать правила 2.0.

Solution:
Сначала вынести только схему, defaults, миграцию и сохранение данных. Сбор
значений из widgets остаётся в UI Adapter до появления project state из Task 1.

Benefits:
Module проходит deletion test: без него правила миграции снова распределятся
между старым UI и wizard. Это основной Seam для совместимости 2.0 → 3.0 и
повышает тестируемость без запуска Qt.

Risk and tests:
- Риск средний: текущие тесты проверяют сохранение через `MainWindow`.
- Покрытие: `test_main_ui_acceptance.py`, `test_cleanup_ui.py`,
  `test_visible_mark_ui.py`, `test_upscale_positions.py`.

## Кандидат 5: сетевые и security primitives

Files:
- `main.py`: exceptions и `HttpsOnlyRedirectHandler`, строки 92–110.
- `main.py`: HTTPS context, bounded read, URL/image validation и redaction,
  строки 482–566.

Problem:
Одинаковые правила доверия используются генерацией, model probe, downloads и
updater, но их Seam находится внутри entry-point файла.

Solution:
Перенести набор как один security Module, оставив временные совместимые
re-export для тестов, которые patch-ят имена в `main`.

Benefits:
Module имеет Depth: маленький набор правил скрывает HTTPS, redirect, size limit
и secret-redaction implementation. Locality особенно важна для security fixes.

Risk and tests:
- Риск средний из-за прямого patching символов `main`.
- Сильное покрытие: `test_kie_routing.py`, `test_security_boundaries.py`,
  `test_main_ui_acceptance.py`.

## Кандидат 6: обновление приложения

Files:
- `main.py`: version parsing, download, checksum и `check_for_updates`,
  примерно строки 6100–6273.

Problem:
Проверка manifest и файла смешана с QMessageBox, логированием и лицензионным
уведомлением.

Solution:
Сначала отделить проверяемое ядро обновления; Qt-решения оставить UI Adapter.

Benefits:
Появится Locality для manifest/download/checksum implementation и узкий тестовый
Seam. UI перестанет знать детали безопасной загрузки.

Risk and tests:
- Риск средний.
- Скачивание, HTTPS и checksum покрыты `test_security_boundaries.py`.

## Кандидат 7: финальная публикация и очистка файла

Files:
- `main.py`: metadata cleanup, trim и atomic final publication, примерно
  строки 1494–1943.

Problem:
Это связная и ценная implementation, но она зависит от множества полей worker,
progress/cancel и файлов промежуточных стадий.

Solution:
Переносить целиком только после конфигурации и security Module, сохраняя тонкий
Worker Adapter для progress и cancellation.

Benefits:
Максимальный Leverage: одна глубокая стадия обслуживает все три режима.
Locality сохраняет атомарность, metadata invariants и правила безопасного
результата.

Risk and tests:
- Риск средний–высокий; выполнять последним из перечисленных.
- Сильное покрытие: `test_final_save_cleanup.py`,
  `test_metadata_cleanup_acceptance.py`, `test_kie_routing.py`.

## Что не следует извлекать первым

### `MainWindow.setup_ui`

Механическое создание файла с теми же сотнями присваиваний `self.*` даст
shallow Module: Interface останется равным почти всей implementation.
Для 3.0 безопаснее создать новый wizard shell рядом со старым UI, подключить его
к project state, а затем удалить старую оболочку после прохождения acceptance.

### `WorkerThread._run_processing_pipeline`

Оркестрация строк 989–1119 имеет высокую Depth, но сейчас её Interface фактически
включает десятки полей и методов `WorkerThread`. Прямое извлечение разрушит
Locality. Сначала нужны seams конфигурации, provider rules, security и final
publication.

### Весь `WorkerThread`

44 его метода прямо затронуты тестами. Массовый перенос одновременно изменит
слишком много seams. На переходе `WorkerThread` должен оставаться Qt Adapter,
пока orchestration постепенно уходит за проверенные Module.

## Рекомендуемый порядок

1. Реализовать независимый project state и маршруты Task 1.
2. Перенести кандидаты 1–2 без изменения поведения.
3. Углубить каталог моделей.
4. Выделить схему конфигурации и миграцию.
5. Перенести security primitives с совместимыми re-export.
6. Отделить ядро updater.
7. После повторного baseline вынести final publication.
8. Только затем проектировать упрощение processing orchestration.

Каждый перенос выполняется отдельным commit: characterization test → перенос без
изменения поведения → 199 baseline tests → commit.
