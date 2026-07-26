# Задачи Clipart Generator 3.0

Основание: `PRD_3.0.ru.md`
Экраны: `UI_WIZARD_3.0.ru.md`
Исследование: `SYNTHID_3_METHOD_BENCHMARK.ru.md`

## Task 1: Зафиксировать контракты состояния проекта и маршрутов

Status: Done

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
- [x] Для каждого режима существует валидный упорядоченный маршрут.
- [x] Переход назад не теряет данные.
- [x] Конфиг 2.0 читается и преобразуется в состояние 3.0.
- [x] Неизвестные старые поля сохраняются или безопасно игнорируются.

Verification:
- [x] `python -m unittest tests.test_v3_project_state -v`

Notes:
- Рискованная основа; выполнить до новых QWidget.
- Вероятные файлы: новый модуль состояния, конфигурация и тесты.
- Реализовано в `v3_project_state.py`; модель не импортирует PyQt6.
- Проверено: 13 focused-тестов, 212 полных тестов и offscreen SMOKE_OK.

## Task 2: Вынести design tokens и базовые компоненты PyQt6

Status: Done

Goal:
Создать нативный shadcn-inspired слой компонентов без React/Tailwind.

Steps:
- Определить цвета, типографику, spacing, radius и состояния focus/error.
- Реализовать `FormCard`, `ModeCard`, `AdvancedSection` и button variants.
- Убрать дублирование inline stylesheet в новых экранах.
- Добавить offscreen component smoke.

Acceptance:
- [x] Компоненты используют единые токены.
- [x] Disabled, focus, warning и error различимы без одного только цвета.
- [x] Компоненты корректны при 980×700.

Verification:
- [x] `$env:QT_QPA_PLATFORM='offscreen'; python -m unittest tests.test_v3_components -v`

Notes:
- Существующий UI пока не переписывать целиком.
- Реализовано в `v3_components.py`; существующий UI не изменён.
- Проверено: 7 focused-тестов, 219 полных тестов, offscreen smoke и визуальное превью 980×700.
- Независимый review-loop: PASS после исправления disabled-state `AdvancedSection`.

## Task 3: Реализовать оболочку wizard

Status: Done

Goal:
Создать `AppShell` с top bar, stepper, `QStackedWidget` и footer navigation.

Steps:
- Реализовать отображение текущего маршрута.
- Связать `Назад/Далее` с моделью состояния.
- Добавить статусы шагов и локальную валидацию.
- Добавить обработку несохранённых изменений при смене режима.

Acceptance:
- [x] Три тестовых маршрута проходят вперёд и назад.
- [x] Невалидный шаг блокирует только переход вперёд.
- [x] Состояние не хранится исключительно внутри widgets.

Verification:
- [x] `python -m unittest tests.test_v3_wizard_navigation -v`
- [x] Offscreen smoke оболочки.

Notes:
- Не подключать реальный pipeline до стабильной навигации.
- Реализовано в `v3_wizard.py`; pipeline не подключён.
- Проверено: 10 focused-тестов, 229 полных тестов, keyboard flow и
  визуальный offscreen smoke при 980×700.
- Независимый review-loop: PASS после защиты ownership страниц и перехода к
  результатам только после `run_requested`.

## Task 4: Создать стартовый экран выбора режима

Status: Done

Goal:
Дать пользователю понятный выбор из клипарта, Pinterest-пинов и обработки.

Steps:
- Реализовать три `ModeCard`.
- Добавить продолжение последнего проекта.
- Добавить доступное описание результата каждого режима.

Acceptance:
- [x] Выбор карточки строит правильный маршрут.
- [x] Pinterest-карточка обещает только изображения по промптам.
- [x] При новом проекте чужие mode-specific значения не протекают между
  режимами.

Verification:
- [x] `python -m unittest tests.test_v3_mode_selection -v`

Notes:
- Реализовано в `v3_mode_selection.py`: три `ModeCard`, snapshot последнего
  проекта и корневой переход к `AppShell`.
- Проверено: 7 focused-тестов, 236 полных тестов, keyboard flow и визуальный
  offscreen smoke при 980×700.
- Независимый review-loop: PASS после добавления явного возврата с экрана смены
  режима и очистки скрытых accessibility-атрибутов.

## Task 5: Реализовать генератор серий промптов

Status: Done

Goal:
Создавать редактируемый согласованный список промптов без обязательного LLM.

Steps:
- Создать схему полей и mode-specific defaults.
- Реализовать детерминированную сборку вариантов.
- Добавить нормализацию, удаление дублей и лимит количества.
- Преобразовать результат в существующий prompt-entry формат.
- Добавить сохранение и восстановление черновика.

Acceptance:
- [x] Одинаковый ввод даёт воспроизводимую серию.
- [x] Клипарт и Pinterest используют разные безопасные defaults.
- [x] Все результаты доступны для ручного редактирования.
- [x] Генератор не выполняет сетевой запрос.

Verification:
- [x] `python -m unittest tests.test_v3_prompt_generator -v`

Notes:
- AI-rewrite оставить расширением за отдельным интерфейсом провайдера.
- Реализовано в `v3_prompt_generator.py` и расширениях `v3_project_state.py`: локальная
  детерминированная генерация, нормализация, дедупликация и сохранение черновика.
- Проверено: 12 focused-тестов, 13 state-тестов и 248 полных тестов; legacy `MainWindow`
  открывается в offscreen-режиме.
- Security review: сетевых и LLM-вызовов нет; размеры входа ограничены, повреждённые черновики
  отклоняются fail-closed.
- Независимый review-loop: PASS после исправления точного количества при максимальных полях и
  строгой проверки границ черновика.

## Task 6: Собрать вертикальный срез режима «Клипарт»

Status: Done

Goal:
Пройти новый маршрут от проекта и промптов до существующего generation pipeline.

Steps:
- Реализовать экраны A1–A6.
- Подключить существующие prompt/reference модели.
- Показать model/ratio/resolution и стоимость.
- Отобразить порядок обработки.
- Адаптировать запуск без дублирования worker logic.

Acceptance:
- [x] Пакет клипарта запускается из wizard.
- [x] Все поддерживаемые 2.0 операции доступны на соответствующем шаге.
- [x] Исходные промпты и файлы не теряются при возврате назад.

Verification:
- [x] `python -m unittest tests.test_v3_clipart_flow -v`
- [x] Существующие generation и pipeline тесты.

Notes:
- Реализованы A1–A6 в `v3_clipart_flow.py`; запуск делегируется существующему
  `WorkerThread`, сетевой и pipeline-код не дублируются.
- Поддержаны prompt/reference-модели, варианты, стоимость, операции 2.0,
  предварительная проверка ключей и локальных референсов.
- Проверено: 23 focused-теста и 271 полный тест, включая существующие
  generation, processing и visible-mark pipeline тесты.
- Security review: runtime-параметры ограничены моделью проекта, секреты не
  сериализуются и не попадают в repr, неизвестные платные модели блокируются.
- Независимый review-loop: PASS после трёх проходов и закрытия findings по
  preflight, redaction, ограничениям ввода и подсчёту платных вызовов.

## Task 7: Собрать вертикальный срез режима «Pinterest-пины»

Status: Done

Goal:
Пакетно создавать изображения пинов по промптам.

Steps:
- Реализовать экраны B1–B5.
- Добавить вертикальный рекомендуемый ratio.
- Подключить prompt generator и существующую генерацию.
- Добавить резюме количества запросов, формата и стоимости.

Acceptance:
- [x] Пользователь получает пакет изображений по списку промптов.
- [x] Нет локального редактора текста, шаблонов или публикации.
- [x] Пользователь может изменить поддерживаемую пропорцию.

Verification:
- [x] `python -m unittest tests.test_v3_pinterest_flow -v`

Notes:
- Реализованы B1–B5 в `v3_pinterest_flow.py` с переиспользованием импорта,
  prompt generator, model catalog, preflight и существующего `WorkerThread`.
- Безопасный default — `gpt-image-2 / 9:16 / 1K`; миграция 2.0 не переносит
  несовместимые clipart-настройки в новый Pinterest-режим.
- Один выбранный model/ratio/resolution детерминированно применяется к обычным
  и reference-промптам; проверено 106 сочетаний поддерживаемых форматов.
- Проверено: 13 focused-тестов, 77 V3-интеграционных и 284 полных теста;
  offscreen smoke всех пяти экранов при 980×700.
- Security review: запуск только явным действием, стоимость видна заранее,
  refs валидируются, secrets redacted, нового network/worker-кода нет.
- Review-loop: три прохода; все findings по формату, миграции и model pairing
  закрыты и подтверждены regression-тестами.

## Task 8: Собрать вертикальный срез режима «Обработка»

Status: Done

Goal:
Провести локальные файлы через выбранный рецепт и существующий pipeline.

Steps:
- Реализовать экраны C1–C3 и C5.
- Добавить drag-and-drop и безопасную карточку файла.
- Реализовать рецепты как preset, а не отдельные pipeline.
- Показать и валидировать порядок операций.

Acceptance:
- [x] Рецепт можно изменить до запуска.
- [x] Недопустимые сочетания объясняются до запуска.
- [x] Исходник не перезаписывается.

Verification:
- [x] `python -m unittest tests.test_v3_processing_flow -v` — 17/17.
- [x] `python -m unittest tests.test_local_processing_acceptance -v` — 8/8.
- [x] Полная регрессия `python -m unittest discover -s tests -p 'test_*.py'` — 301/301.
- [x] Offscreen UI smoke 980×700 для C1/C3/C5.
- [x] Review loop — 3 прохода; все найденные блокеры исправлены и покрыты regression-тестами.
- [x] Security: тип/размер/декодирование файлов, batch-limit, collision preflight, explicit consent, fail-closed providers, secret/path-safe errors.

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
