# Задачи Clipart Generator 3.0

Основание: `PRD_3.0.ru.md`
Экраны: `UI_WIZARD_3.0.ru.md`
Исследование: `SYNTHID_3_METHOD_BENCHMARK.ru.md`

## Task 1: Зафиксировать контракты состояния проекта и маршрутов

Status: Ready

Goal:
Создать независимую от QWidget модель проекта 3.0, трёх режимов, шагов,
валидации и сохранения черновика.

Steps:
- Описать enum режимов и идентификаторы шагов.
- Описать данные клипарта, Pinterest и обработки.
- Отделить mode-specific настройки от общих.
- Добавить миграцию чтения конфигурации 2.0 без разрушительного изменения.
- Добавить unit-тесты переходов и сериализации.

Acceptance:
- [ ] Для каждого режима существует валидный упорядоченный маршрут.
- [ ] Переход назад не теряет данные.
- [ ] Конфиг 2.0 читается и преобразуется в состояние 3.0.
- [ ] Неизвестные старые поля сохраняются или безопасно игнорируются.

Verification:
- [ ] `python -m unittest tests.test_v3_project_state -v`

Notes:
- Рискованная основа; выполнить до новых QWidget.
- Вероятные файлы: новый модуль состояния, конфигурация и тесты.

## Task 2: Вынести design tokens и базовые компоненты PyQt6

Status: Todo

Goal:
Создать нативный shadcn-inspired слой компонентов без React/Tailwind.

Steps:
- Определить цвета, типографику, spacing, radius и состояния focus/error.
- Реализовать `FormCard`, `ModeCard`, `AdvancedSection` и button variants.
- Убрать дублирование inline stylesheet в новых экранах.
- Добавить offscreen component smoke.

Acceptance:
- [ ] Компоненты используют единые токены.
- [ ] Disabled, focus, warning и error различимы без одного только цвета.
- [ ] Компоненты корректны при 980×700.

Verification:
- [ ] `$env:QT_QPA_PLATFORM='offscreen'; python -m unittest tests.test_v3_components -v`

Notes:
- Существующий UI пока не переписывать целиком.

## Task 3: Реализовать оболочку wizard

Status: Todo

Goal:
Создать `AppShell` с top bar, stepper, `QStackedWidget` и footer navigation.

Steps:
- Реализовать отображение текущего маршрута.
- Связать `Назад/Далее` с моделью состояния.
- Добавить статусы шагов и локальную валидацию.
- Добавить обработку несохранённых изменений при смене режима.

Acceptance:
- [ ] Три тестовых маршрута проходят вперёд и назад.
- [ ] Невалидный шаг блокирует только переход вперёд.
- [ ] Состояние не хранится исключительно внутри widgets.

Verification:
- [ ] `python -m unittest tests.test_v3_wizard_navigation -v`
- [ ] Offscreen smoke оболочки.

Notes:
- Не подключать реальный pipeline до стабильной навигации.

## Task 4: Создать стартовый экран выбора режима

Status: Todo

Goal:
Дать пользователю понятный выбор из клипарта, Pinterest-пинов и обработки.

Steps:
- Реализовать три `ModeCard`.
- Добавить продолжение последнего проекта.
- Добавить доступное описание результата каждого режима.

Acceptance:
- [ ] Выбор карточки строит правильный маршрут.
- [ ] Pinterest-карточка обещает только изображения по промптам.
- [ ] При новом проекте чужие mode-specific значения не протекают между
  режимами.

Verification:
- [ ] `python -m unittest tests.test_v3_mode_selection -v`

## Task 5: Реализовать генератор серий промптов

Status: Todo

Goal:
Создавать редактируемый согласованный список промптов без обязательного LLM.

Steps:
- Создать схему полей и mode-specific defaults.
- Реализовать детерминированную сборку вариантов.
- Добавить нормализацию, удаление дублей и лимит количества.
- Преобразовать результат в существующий prompt-entry формат.
- Добавить сохранение и восстановление черновика.

Acceptance:
- [ ] Одинаковый ввод даёт воспроизводимую серию.
- [ ] Клипарт и Pinterest используют разные безопасные defaults.
- [ ] Все результаты доступны для ручного редактирования.
- [ ] Генератор не выполняет сетевой запрос.

Verification:
- [ ] `python -m unittest tests.test_v3_prompt_generator -v`

Notes:
- AI-rewrite оставить расширением за отдельным интерфейсом провайдера.

## Task 6: Собрать вертикальный срез режима «Клипарт»

Status: Todo

Goal:
Пройти новый маршрут от проекта и промптов до существующего generation pipeline.

Steps:
- Реализовать экраны A1–A6.
- Подключить существующие prompt/reference модели.
- Показать model/ratio/resolution и стоимость.
- Отобразить порядок обработки.
- Адаптировать запуск без дублирования worker logic.

Acceptance:
- [ ] Пакет клипарта запускается из wizard.
- [ ] Все поддерживаемые 2.0 операции доступны на соответствующем шаге.
- [ ] Исходные промпты и файлы не теряются при возврате назад.

Verification:
- [ ] `python -m unittest tests.test_v3_clipart_flow -v`
- [ ] Существующие generation и pipeline тесты.

## Task 7: Собрать вертикальный срез режима «Pinterest-пины»

Status: Todo

Goal:
Пакетно создавать изображения пинов по промптам.

Steps:
- Реализовать экраны B1–B5.
- Добавить вертикальный рекомендуемый ratio.
- Подключить prompt generator и существующую генерацию.
- Добавить резюме количества запросов, формата и стоимости.

Acceptance:
- [ ] Пользователь получает пакет изображений по списку промптов.
- [ ] Нет локального редактора текста, шаблонов или публикации.
- [ ] Пользователь может изменить поддерживаемую пропорцию.

Verification:
- [ ] `python -m unittest tests.test_v3_pinterest_flow -v`

## Task 8: Собрать вертикальный срез режима «Обработка»

Status: Todo

Goal:
Провести локальные файлы через выбранный рецепт и существующий pipeline.

Steps:
- Реализовать экраны C1–C3 и C5.
- Добавить drag-and-drop и безопасную карточку файла.
- Реализовать рецепты как preset, а не отдельные pipeline.
- Показать и валидировать порядок операций.

Acceptance:
- [ ] Рецепт можно изменить до запуска.
- [ ] Недопустимые сочетания объясняются до запуска.
- [ ] Исходник не перезаписывается.

Verification:
- [ ] `python -m unittest tests.test_v3_processing_flow -v`
- [ ] Существующие local processing acceptance tests.

## Task 9: Реализовать центр проверки и очистки

Status: Todo

Goal:
Показывать file hints, C2PA и pixel evidence как независимые категории.

Steps:
- Реализовать три `EvidenceCard`.
- Подключить существующие metadata/C2PA inspector и cleanup.
- Добавить официальный Gemini и OpenAI handoff без auto-upload.
- Добавить ввод нормализованного результата пользователем.
- Обеспечить безопасный экспорт отчёта.

Acceptance:
- [ ] Metadata cleanup не меняет `pixel_evidence`.
- [ ] `not_detected` не отображается как «создано человеком».
- [ ] Внешняя проверка не отправляет файл автоматически.
- [ ] Лог не содержит путей, prompt, metadata values или ключей.

Verification:
- [ ] `python -m unittest tests.test_v3_evidence_center -v`
- [ ] Существующие watermark status и security tests.

## Task 10: Реализовать общий экран выполнения и результатов

Status: Todo

Goal:
Дать единое наблюдаемое выполнение для всех режимов.

Steps:
- Реализовать очередь, общий прогресс и статус файла.
- Добавить безопасную остановку после текущего файла.
- Добавить before/after, повтор ошибок и открытие папки.
- Сохранить завершённые результаты при ошибке следующего файла.

Acceptance:
- [ ] Ошибка одного файла не скрывает успешные результаты.
- [ ] Отмена не оставляет частично перезаписанный output.
- [ ] Пользователь видит краткую причину и может открыть технический лог.

Verification:
- [ ] `python -m unittest tests.test_v3_run_queue -v`

## Task 11: Выполнить M1 pilot reverse-SynthID

Status: Todo

Goal:
Получить воспроизводимые результаты M1 на основном наборе без изменения
окружения приложения.

Steps:
- Провести license/security review и зафиксировать commit SHA.
- Создать изолированную среду и закрыть auto-update.
- Подтвердить официально обнаруживаемые входы.
- Выполнить два разрешённых профиля.
- Собрать evidence, fidelity и resource metrics.

Acceptance:
- [ ] Все результаты связаны с SHA-256 входа, commit и параметрами.
- [ ] Исходники неизменны.
- [ ] `processing` и `pixel_evidence` разделены.

Verification:
- [ ] Повтор одного профиля даёт сопоставимый отчёт.
- [ ] Ручная проверка manifest и contact sheet.

Notes:
- Никаких заявлений об удалении до официальной проверки выхода.

## Task 12: Выполнить M2 pilot CtrlRegen

Status: Todo

Goal:
Проверить малосильную diffusion-реконструкцию в изолированной среде.

Steps:
- Зафиксировать source/model revisions и лицензии.
- Пройти hardware/disk preflight до загрузки весов.
- При локальном no-go остановиться без forced CPU run.
- Для cloud-варианта отдельно согласовать провайдера, privacy и лимит цены.
- Выполнить разрешённые профили и собрать метрики.

Acceptance:
- [ ] Нет скрытой загрузки файлов или неограниченного расхода.
- [ ] Изменение деталей и alpha измерено.
- [ ] No-go является допустимым воспроизводимым результатом.

Verification:
- [ ] Проверка benchmark manifest, cost ledger и official evidence.

## Task 13: Выполнить M3 pilot Qwen/Canny

Status: Todo

Goal:
Проверить structure-guided реконструкцию на тех же входах.

Steps:
- Зафиксировать workflow, source/model revisions и лицензии.
- Выполнить hardware preflight.
- При необходимости подготовить отдельно согласованный GPU worker/cloud run.
- Запустить не более двух профилей на вход.
- Собрать визуальные, evidence и operational metrics.

Acceptance:
- [ ] Текст, лицо, композиция и alpha оценены отдельно.
- [ ] Провайдер и стоимость полностью указаны.
- [ ] В Git не сохранены изображения или секреты без отдельного решения.

Verification:
- [ ] Проверка benchmark manifest, contact sheet и official evidence.

## Task 14: Принять SynthID architecture decision

Status: Todo

Goal:
По одинаковым правилам выбрать `adopt_local_experimental`,
`adopt_worker_experimental`, `research_only` или `reject`.

Steps:
- Свести результаты M1–M3.
- Проверить pilot gates.
- Провести privacy, license, cost и packaging review победителя.
- Записать ADR/DECISION без маркетингового преувеличения.
- При pass создать отдельные implementation tasks; при fail не добавлять control.

Acceptance:
- [ ] Решение опирается на официальные before/after evidence.
- [ ] Малый pilot не представлен как универсальное доказательство.
- [ ] До решения production UI не содержит работающей SynthID-перегенерации.

Verification:
- [ ] Независимая проверка отчёта и соответствия
  `PIXEL_WATERMARK_STATUS_CONTRACT.md`.

## Task 15: Регрессия, миграция и release readiness 3.0

Status: Todo

Goal:
Подтвердить сохранность функций 2.0 и готовность нового wizard.

Steps:
- Прогнать unit, integration, security и offscreen UI tests.
- Проверить миграцию реального обезличенного конфига 2.0.
- Проверить Windows/macOS сборку без публикации.
- Обновить пользовательскую документацию и changelog.
- Провести ручной smoke трёх маршрутов.

Acceptance:
- [ ] Все обязательные критерии PRD выполнены.
- [ ] Существующий pipeline не потерял поддерживаемые возможности.
- [ ] Нет секретов, benchmark outputs или пользовательских файлов в release.
- [ ] Release/tag/publish выполняются только отдельной задачей.

Verification:
- [ ] `python -m unittest discover -s tests -v`
- [ ] `python -m py_compile main.py`
- [ ] Offscreen `MainWindow` smoke.
- [ ] Отдельные build checks Windows/macOS.

Notes:
- Следующий рекомендованный workflow реализации: `$code-vibecoding-workflow`.
