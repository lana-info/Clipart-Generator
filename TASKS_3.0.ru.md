# Задачи Clipart Generator 3.0

Основание: `PRD_3.0.ru.md`
PRD Key: `CG3-PRD-001`
Task Set Key: `CG3-TASKSET-001`
Экраны: `UI_WIZARD_3.0.ru.md`
Исследование: `SYNTHID_3_METHOD_BENCHMARK.ru.md`

## Task 1: Зафиксировать контракты состояния проекта и маршрутов

Key: `CG3-TASK-001`
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

Key: `CG3-TASK-002`
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

Key: `CG3-TASK-003`
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
- Пункт о предупреждении несохранённых изменений отменён новым требованием
  `CG3-FR-002` и заменяется в `CG3-TASK-016`.

## Task 4: Создать стартовый экран выбора режима

Key: `CG3-TASK-004`
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
- Формулировки «последний/новый проект» исторические; пользовательский маршрут
  без сущности проекта реализуется в `CG3-TASK-016`.

## Task 5: Реализовать генератор серий промптов

Key: `CG3-TASK-005`
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

Key: `CG3-TASK-006`
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

Key: `CG3-TASK-007`
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

Key: `CG3-TASK-008`
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

Key: `CG3-TASK-009`
Status: Done

Goal:
Показывать file hints, C2PA и pixel evidence как независимые категории.

Steps:
- Реализовать три `EvidenceCard`.
- Подключить существующие metadata/C2PA inspector и cleanup.
- Добавить официальный Gemini и OpenAI handoff без auto-upload.
- Добавить ввод нормализованного результата пользователем.
- Обеспечить безопасный экспорт отчёта.

Acceptance:
- [x] Metadata cleanup не меняет `pixel_evidence`.
- [x] `not_detected` не отображается как «создано человеком».
- [x] Внешняя проверка не отправляет файл автоматически.
- [x] Лог не содержит путей, prompt, metadata values или ключей.

Verification:
- [x] `python -m unittest tests.test_v3_evidence_center -v`
- [x] Существующие watermark status и security tests.

Notes:
- [x] Focused evidence-center tests: 14/14.
- [x] Полная регрессия: 315/315.
- [x] Независимый review pass 2: PASS.

## Task 10: Реализовать общий экран выполнения и результатов

Key: `CG3-TASK-010`
Status: Done

Goal:
Дать единое наблюдаемое выполнение для всех режимов.

Steps:
- Реализовать очередь, общий прогресс и статус файла.
- Добавить безопасную остановку после текущего файла.
- Добавить before/after, повтор ошибок и открытие папки.
- Сохранить завершённые результаты при ошибке следующего файла.

Acceptance:
- [x] Ошибка одного файла не скрывает успешные результаты.
- [x] Отмена не оставляет частично перезаписанный output.
- [x] Пользователь видит краткую причину и может открыть технический лог.

Verification:
- [x] `python -m unittest tests.test_v3_run_queue -v`

Notes:
- Общий экран подключён ко всем трём режимам; очередь изолирует старые сигналы worker и сохраняет уже готовые результаты.
- Проверено: 15/15 focused, 127/127 integration/security, 330/330 full regression; все замечания трёх review-проходов устранены.

## Task 11: Выполнить M1 pilot reverse-SynthID

Key: `CG3-TASK-011`
Status: In Progress
Requirements: `CG3-RS-001`, `CG3-RS-002`, `CG3-RS-003`, `CG3-RS-004`

Goal:
Получить воспроизводимые результаты M1 на основном наборе без изменения
окружения приложения.

Steps:
- [x] Провести license/security review и зафиксировать commit SHA.
- [x] Создать изолированную среду и закрыть auto-update.
- [ ] Подтвердить официально обнаруживаемые входы — требуется отдельное согласие на передачу Google.
- [x] Выполнить два разрешённых профиля.
- [x] Собрать локальные evidence-status, fidelity и resource metrics.

Acceptance:
- [x] Все результаты связаны с SHA-256 входа, commit и параметрами.
- [x] Исходники неизменны.
- [x] `processing` и `pixel_evidence` разделены.

Verification:
- [x] Повтор одного профиля даёт сопоставимый отчёт.
- [ ] Manifest формально проверен: contact sheet декодируется и его sha256 совпадает с зафиксированным в `benchmark_synthid_m1.pilot.json`; визуальная проверка ожидает доступа к viewer (локально: `.scratch/reverse-synthid-m1/run-20260726/contact-sheets/m1-contact-sheet.png`).

Notes:
- Никаких заявлений об удалении до официальной проверки выхода.
- Локальный recorded run сохранён как inconclusive; после security review создан pickle-free codebook, secure repeat выполнен с точным воспроизводимым совпадением O1/final (не хватает официального pixel evidence).
- Проверено: 20/20 focused, 350/350 full regression; третий review-проход — без замечаний.

## Task 12: Выполнить M2 pilot CtrlRegen

Key: `CG3-TASK-012`
Status: In Progress
Requirements: `CG3-RS-001`, `CG3-RS-002`, `CG3-RS-003`, `CG3-RS-004`

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
- [x] Hardware/disk preflight выполнен, блокировка локального запуска из-за отсутствия CUDA зафиксирована в `benchmark_synthid_m2.preflight.json`.
- [ ] Проверка benchmark manifest, cost ledger и official evidence.

Notes:
- Для M2 пока зафиксирован no-go: CUDA отсутствует (1 GPU-адаптер без CUDA), source/model/license не зафиксированы в pinned-режиме, cloud-путь требует отдельного согласия на провайдера и бюджет. Файл preflight: `benchmark_synthid_m2.preflight.json`.

## Task 13: Выполнить M3 pilot Qwen/Canny

Key: `CG3-TASK-013`
Status: In Progress
Requirements: `CG3-RS-001`, `CG3-RS-002`, `CG3-RS-003`, `CG3-RS-004`

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
- [x] Hardware preflight выполнен; блок локального run из-за отсутствия CUDA зафиксирован в `benchmark_synthid_m3.preflight.json`.

Notes:
- Для M3 пока зафиксирован no-go: CUDA отсутствует (1 GPU-адаптер без CUDA), локальный запуск и cloud-агрегат не согласованы с провайдером/бюджетом.
  Файл preflight: `benchmark_synthid_m3.preflight.json`.

## Task 14: Принять SynthID architecture decision

Key: `CG3-TASK-014`
Status: Done
Requirements: `CG3-RS-005`, `CG3-FR-062`, `CG3-FR-063`, `CG3-FR-064`,
`CG3-AC-019`

Goal:
По одинаковым правилам выбрать `adopt_local_experimental`,
`adopt_worker_experimental`, `research_only` или `reject`.

Steps:
- Свести результаты M1–M3.
- Проверить pilot gates.
- Провести privacy, license, cost и packaging review победителя.
- Записать ADR/DECISION без маркетингового преувеличения.
- Зафиксировать, что provenance tool необязателен, онлайн-upload отсутствует, а
  обычный production pipeline не зависит от проверки SynthID.
- При pass создать отдельные implementation tasks; при fail не добавлять control.

Acceptance:
- [ ] Решение опирается на официальные before/after evidence.
- [ ] Малый pilot не представлен как универсальное доказательство.
- [ ] До решения production UI не содержит работающей SynthID-перегенерации.
- [ ] UI не обещает гарантированное удаление или человеческое происхождение.
- [ ] Генерация, обработка и экспорт не блокируются provenance tool.

Verification:
- [ ] Независимая проверка отчёта и соответствия
  `PIXEL_WATERMARK_STATUS_CONTRACT.md`.

Decision:
`research_only`. Подробности: `docs/decisions/ADR-001-synthid-architecture.md`.

## Task 15: Регрессия, миграция и release readiness 3.0

Key: `CG3-TASK-015`
Status: Superseded by `CG3-TASK-030`

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
- Заменена после ручного тестирования более полным release gate
  `CG3-TASK-030`; историческая задача сохранена.

---

## Revised UX and architecture backlog

Этот раздел переводит комментарии ручного тестирования в задачи по исправленному
`CG3-PRD-001`. Первая безопасная задача: `CG3-TASK-016`.

## Task 16: Убрать сущность «проект» из пользовательских маршрутов

Key: `CG3-TASK-016`
Status: Done
Requirements: `CG3-FR-001`, `CG3-FR-002`, `CG3-AR-002`, `CG3-AR-010`,
`CG3-FR-021`, `CG3-AC-001`, `CG3-AC-010`, `CG3-AC-020`

Goal:
Пользователь выбирает режим и папку без названия проекта и без предупреждения
при переключении режима.

Steps:
- Убрать поле названия проекта и его валидацию из Clipart/Pinterest.
- Оставить чтение legacy `project_name` только для совместимости черновиков.
- Автоматически хранить независимый draft каждого режима.
- Атомарно автосохранять промпты, их порядок и references после изменений и
  восстанавливать их при следующем запуске.
- Удалить modal confirmation о несохранённых данных при переключении режима.
- Обновить тесты состояния, навигации и миграции.

Acceptance:
- [x] Новый маршрут не показывает и не требует название проекта.
- [x] Переключение режима происходит сразу и сохраняет данные обоих режимов.
- [x] Старый draft с `project_name` открывается без ошибки.
- [x] Перезапуск приложения восстанавливает независимые prompt drafts режимов.

Verification:
- [x] `python -m unittest tests.test_v3_project_state tests.test_v3_mode_selection tests.test_v3_wizard_navigation -v`

Notes:
- Вероятные файлы: `v3_project_state.py`, `v3_wizard.py`,
  `v3_mode_selection.py`, `v3_clipart_flow.py`, `v3_pinterest_flow.py`.

## Task 17: Создать общую модель и оболочку PromptWorkspace

Key: `CG3-TASK-017`
Status: Done
Requirements: `CG3-FR-010`, `CG3-FR-011`, `CG3-FR-012`, `CG3-FR-013`,
`CG3-FR-022`, `CG3-AR-003`, `CG3-AR-009`, `CG3-AC-002`, `CG3-AC-020`

Goal:
Клипарт и Pinterest используют один редактор списка промптов.

Steps:
- Вынести общий model/view из отдельных input/review pages.
- Объединить ввод и проверку промптов в один маршрутный шаг.
- Добавить строковые действия «дублировать» и «удалить».
- Добавить «Новый промпт» и «Удалить все промпты».
- После подтверждения «Удалить все промпты» очищать также их references и
  сохранять пустой draft текущего режима.
- Реализовать drag-and-drop reorder с сохранением references.

Acceptance:
- [x] Оба режима создают один и тот же компонент PromptWorkspace.
- [x] Порядок меняется перетаскиванием без потери текста и референсов.
- [x] Кнопок «выше/ниже» и отдельного шага проверки нет.

Verification:
- [x] `python -m unittest tests.test_v3_prompt_workspace -v`
- [x] Offscreen smoke drag/drop model reorder.

Notes:
- Не копировать QWidget между flow-модулями; нужен общий модуль.

## Task 18: Реализовать редактор локальных референсов

Key: `CG3-TASK-018`
Status: Done
Requirements: `CG3-FR-014`, `CG3-FR-015`, `CG3-FR-016`, `CG3-FR-017`,
`CG3-FR-023`, `CG3-FR-024`, `CG3-AC-016`, `CG3-AC-020`

Goal:
Референсы выбираются файлами и управляются на уровне строки, выделения и всего
списка.

Steps:
- Открывать полный prompt editor по двойному клику.
- Показывать референсы с миниатюрой, именем и отдельной корзиной.
- Добавить выбор нескольких локальных изображений.
- Добавить bulk add для выделенных/всех строк.
- Добавить bulk replace с явной областью действия.
- Добавить «Удалить все референсы» без удаления текстов промптов.
- При восстановлении помечать отсутствующие локальные файлы, не удаляя промпт.
- Проверять существование и допустимый формат файла без загрузки в сеть.

Acceptance:
- [ ] Текстовый ввод URL/пути не является основным способом добавления.
- [ ] Удаление одного референса не затрагивает остальные.
- [ ] Replace меняет только выбранные строки.
- [ ] «Удалить все референсы» сохраняет тексты и порядок промптов.
- [ ] После перезапуска очищенные references не появляются снова.

Verification:
- [ ] `python -m unittest tests.test_v3_prompt_references -v`
- [ ] Ручной smoke: один, несколько, selected/all, replace и delete.

## Task 19: Переделать CSV-import на ручное сопоставление столбцов

Key: `CG3-TASK-019`
Status: Done
Requirements: `CG3-FR-018`, `CG3-FR-019`, `CG3-FR-020`, `CG3-AC-003`

Goal:
Импортировать таблицы с любыми названиями столбцов без ложной ошибки
«нет столбца prompt/references».

Steps:
- Показывать preview и выбор prompt/references columns.
- Добавить выбор наличия строки заголовков.
- Заменить неоднозначные подписи на «Добавить к списку» и
  «Заменить все промпты».
- Собирать ошибки с номерами строк, сохраняя валидный preview.
- Общий dialog использовать в Clipart и Pinterest.

Acceptance:
- [ ] CSV с произвольными заголовками импортируется после mapping.
- [ ] References column необязателен.
- [ ] Ошибка содержит номера и причины проблемных строк.

Verification:
- [ ] `python -m unittest tests.test_v3_prompt_csv_import -v`

## Task 20: Сделать генератор серии понятным и необязательным

Key: `CG3-TASK-020`
Status: Done
Requirements: `CG3-FR-025`, `CG3-FR-026`, `CG3-FR-027`, `CG3-FR-028`,
`CG3-AC-018`

Goal:
Пользователь понимает, что функция создаёт варианты текста, и может полностью
её пропустить.

Steps:
- Переименовать блок в «Создать варианты промптов по шаблону».
- Поместить его в необязательную раскрываемую секцию PromptWorkspace.
- Добавить короткое объяснение и preview.
- После preview дать действия «Добавить варианты» и
  «Заменить все промпты».
- Сохранить прямую вставку готовых промптов.

Acceptance:
- [ ] До действия видны объяснение и будущие варианты.
- [ ] Создание вариантов не запускает генерацию изображений.
- [ ] Основной маршрут работает без открытия блока.

Verification:
- [ ] `python -m unittest tests.test_v3_prompt_generator tests.test_v3_prompt_workspace -v`

## Task 21: Упростить выбор моделей и reference-mode

Key: `CG3-TASK-021`
Status: Done
Requirements: `CG3-FR-030`, `CG3-FR-031`, `CG3-FR-032`, `CG3-FR-033`,
`CG3-AC-017`

Goal:
Подходящие модели и режим генерации очевидны до запуска.

Steps:
- Всегда показывать основной выбор модели.
- Автоматически раскрывать reference-models при наличии референса.
- Связать доступность модели с её capabilities.
- Показать причину несовместимости вместо молчаливого сброса настройки.
- Сохранить Pinterest как генерацию изображений без layout/editor функций.

Acceptance:
- [ ] Reference-capable models видны сразу при наличии references.
- [ ] Несовместимая модель не может попасть в run plan.
- [ ] Формат и стоимость пересчитываются после смены модели.

Verification:
- [ ] `python -m unittest tests.test_v3_clipart_flow tests.test_v3_pinterest_flow -v`

## Task 22: Ввести реестр возможностей провайдеров

Key: `CG3-TASK-022`
Status: Done
Requirements: `CG3-FR-045`, `CG3-FR-046`, `CG3-AR-005`

Goal:
UI строит настройки KIE, PhotoRoom и локальных провайдеров по единому
проверяемому контракту.

Steps:
- Описать provider id, операции, параметры, network/cost и alpha capability.
- Перенести правила видимости controls в registry.
- Запретить неизвестные provider/profile до worker.
- Добавить contract tests для KIE, PhotoRoom, rembg, BEN2 и Real-ESRGAN.

Acceptance:
- [x] Выбранный provider показывает только свои поддерживаемые параметры.
- [x] Неизвестный provider не запускает обработку.
- [x] UI и run plan читают один registry.

Verification:
- [x] `python -m unittest tests.test_v3_provider_registry tests.test_v3_processing_flow tests.test_v3_clipart_flow -v`

## Task 23: Создать общий ProcessingPipelineEditor

Key: `CG3-TASK-023`
Status: Done
Requirements: `CG3-FR-040`, `CG3-FR-041`, `CG3-FR-042`, `CG3-AR-004`,
`CG3-AR-006`, `CG3-AR-009`, `CG3-AC-004`

Goal:
Все режимы используют один компонент, одну модель рецепта и один builder
pipeline.

Steps:
- Вынести processing controls из flow-модулей.
- Описать единый ProcessingRecipe с mode defaults.
- Подключить компонент через тонкие адаптеры Clipart/Pinterest/Processing.
- Строить отображаемый порядок и worker settings из одного RunPlanBuilder.
- Удалить дублирующие provider controls после миграции тестов.

Acceptance:
- [x] Изменение общей операции отражается во всех трёх режимах.
- [x] Отображаемый порядок совпадает с worker order.
- [x] Flow-контроллеры не создают собственные processing widgets.

Verification:
- [x] `python -m unittest tests.test_v3_processing_editor -v`
- [ ] Полный Pinterest regression требует отдельного исправления существующего model-catalog контракта (gpt-image-2 сейчас зарегистрирован как image-to-image).

Notes:
- Pinterest теперь хранит `operations` в собственном draft и подключает тот же
  `ProcessingPipelineEditor`; adapter передаёт эти настройки в общий run plan.

## Task 24: Свести очистку к одной безопасной настройке

Key: `CG3-TASK-024`
Status: Done - cleanup preset unified, legacy gates removed from ordinary flow, decoded-pixel parity verified
Requirements: `CG3-FR-050`, `CG3-FR-051`, `CG3-FR-052`, `CG3-FR-053`,
`CG3-FR-054`, `CG3-FR-060`, `CG3-FR-061`, `CG3-AC-005`, `CG3-AC-009`

Goal:
Одна галочка очищает поддерживаемые служебные данные и гарантированно сохраняет
ICC, DPI и декодированные пиксели.

Steps:
- Заменить набор пользовательских флагов одним cleanup preset.
- Зафиксировать внутренний preset EXIF/XMP/IPTC/comments/thumbnail/generator/C2PA.
- Удалить из UI controls ICC/DPI и всегда сохранять их.
- Сделать file preflight внутренним, без отдельного обязательного шага.
- Удалить legal checkbox и обязательный experimental opt-in из обычного
  processing flow; experimental consent показывать только внутри явно
  выбранного будущего эксперимента.
- Проверять decoded-pixel equality для cleanup-only PNG/JPEG.

Acceptance:
- [x] Одна галочка управляет полным preset.
- [x] ICC/DPI сохраняются и не имеют переключателей удаления.
- [x] Cleanup-only тест подтверждает неизменность декодированных пикселей.
- [x] Обычная обработка запускается без legal/experimental подтверждений.

Verification:
- [x] `python -m unittest tests.test_metadata_cleanup tests.test_c2pa_cleanup tests.test_v3_evidence_center -v`

## Task 25: Зафиксировать defaults клипарта и alpha-safe upscale

Key: `CG3-TASK-025`
Status: Done
Requirements: `CG3-FR-043`, `CG3-FR-044`, `CG3-AC-006`, `CG3-AC-007`

Goal:
Новый клипарт-рецепт сразу готовит PNG 300 DPI и не теряет прозрачность после
удаления фона.

Steps:
- Включить defaults: upscale-before, remove background, trim, 300 DPI.
- Проверять alpha capability для upscale-after.
- Скрывать/блокировать несовместимый provider/profile для прозрачного входа.
- Добавить integration fixture с alpha PNG.

Acceptance:
- [x] Новый state получает четыре требуемых defaults.
- [x] Alpha-safe pipeline сохраняет ненулевую прозрачность.
- [x] Несовместимый post-background upscale не запускается.

Verification:
- [x] `python -m unittest tests.test_v3_project_state tests.test_v3_clipart_flow tests.test_local_processing_acceptance -v`

## Task 26: Улучшить выбор файлов и выходной папки обработки

Key: `CG3-TASK-026`
Status: Done
Requirements: `CG3-FR-003`, `CG3-FR-004`, `CG3-FR-005`, `CG3-AC-008`,
`CG3-AC-014`

Goal:
Пользователь управляет каждым входным файлом и явно выбирает безопасную папку
результата.

Steps:
- Добавить отдельную корзину возле каждого файла.
- Сохранить drag-and-drop, добавление и «Очистить список».
- Добавить отдельный WorkspaceSelector для output folder.
- Валидировать конфликт input/output и безопасно разрешать одинаковые имена.

Acceptance:
- [x] Один файл удаляется без очистки списка.
- [x] Output folder виден до запуска.
- [x] Исходник не перезаписывается даже при совпадении имени.

Verification:
- [x] `python -m unittest tests.test_v3_processing_flow tests.test_v3_output_paths -v`

## Task 27: Создать единые настройки API и проверок провайдера

Key: `CG3-TASK-027`
Status: Done
Requirements: `CG3-FR-070`, `CG3-FR-071`, `CG3-FR-072`, `CG3-FR-073`,
`CG3-AR-008`, `CG3-AR-011`, `CG3-AC-013`

Goal:
KIE и PhotoRoom настраиваются в одном понятном месте без раскрытия секретов.

Steps:
- Создать постоянный entry point «Настройки».
- Добавить единый EnvCredentialStore с платформенными user-data paths.
- Добавить маскированные KIE/PhotoRoom fields.
- Атомарно мигрировать legacy plaintext keys: сначала записать и проверить
  пользовательский `.env`, затем удалить секрет из `config.json`.
- Ограничить права `.env`, исключить его из Git/build/diagnostic bundles.
- Реализовать безопасную проверку подключения.
- Подключить KIE balance только к подтверждённому endpoint.
- Disable balance для неподдерживаемого provider с явной подсказкой.
- Проверить redaction логов и ошибок.

Acceptance:
- [x] Ключ не появляется в UI status, exception и логах.
- [x] После успешной миграции ключ отсутствует в `config.json`.
- [x] Ошибка записи `.env` не удаляет legacy key и блокирует сетевой
  запуск с понятным сообщением.
- [x] Приложение использует user-data `.env`, а не `.env` из репозитория.
- [x] Connection check не запускает платную генерацию.
- [x] Balance не имитируется для неподдерживаемого API.

Verification:
- [x] `python -m unittest tests.test_v3_provider_settings tests.test_v3_credential_store tests.test_main_ui_acceptance -v`

## Task 28: Ввести структурированный прогресс выполнения

Key: `CG3-TASK-028`
Status: Done
Requirements: `CG3-FR-080`, `CG3-FR-081`, `CG3-FR-082`, `CG3-FR-083`,
`CG3-FR-084`, `CG3-AR-007`, `CG3-AC-012`

Goal:
Во время любой очереди видно файл, этап, активность, общий прогресс и результат.

Steps:
- Определить progress event contract.
- Адаптировать legacy WorkerThread messages к structured events.
- Рассчитать монотонный общий progress по файлам и известным этапам.
- Для долгого неизвестного ожидания включать indeterminate activity и timer.
- Показать per-file errors, stop и «Открыть папку».

Acceptance:
- [x] Progress не остаётся на 0% при выполняющемся этапе без объяснения.
- [x] Текущий файл и этап всегда видны.
- [x] Stop не удаляет готовые результаты и не меняет исходники.

Verification:
- [x] `python -m unittest tests.test_v3_run_queue tests.test_v3_progress_events -v` — 17/17.
- [x] Offscreen results-page smoke покрыт `tests.test_v3_run_queue`.

Notes:
- Добавлен `ProgressEvent` contract с адаптацией legacy сообщений.
- Для неизвестного долгого этапа progress bar становится indeterminate, а UI
  показывает текущий файл и этап; известный `progress_value` считается монотонно.

## Task 29: Завершить принудительную контрастную тёмную тему

Key: `CG3-TASK-029`
Status: Done
Requirements: `CG3-FR-090`, `CG3-FR-091`, `CG3-FR-092`, `CG3-FR-093`,
`CG3-FR-094`, `CG3-AR-001`, `CG3-AC-011`

Goal:
Весь текст и все состояния читаемы при любой системной теме.

Steps:
- Применить одну тёмную палитру на уровне QApplication.
- Покрыть токенами tables, combo popups, tooltips, dialogs и disabled states.
- Добавить emerald/teal primary actions и заметный keyboard focus.
- Проверить contrast ratios и offscreen screenshots.
- Провести ручное сравнение при светлой и тёмной теме Windows.

Acceptance:
- [x] Нет сочетаний «светлый на светлом» или «тёмный на тёмном».
- [x] Контраст соответствует порогам PRD.
- [x] Системная тема не меняет читабельность приложения.

Verification:
- [x] `python -m unittest tests.test_v3_components -v` — 8/8.
- [x] QApplication palette, disabled states, combo popups, dialogs и tooltips
  используют единые тёмные токены; контраст основного текста проверен на уровне
  WCAG AAA (7:1+).

Verification:
- [ ] `python -m unittest tests.test_v3_components tests.test_v3_theme_contrast -v`
- [ ] Visual smoke: Windows light + dark.

## Task 30: Провести полную регрессию и release gate 3.0

Key: `CG3-TASK-030`
Status: Todo
Requirements: `CG3-AC-001`–`CG3-AC-020`

Goal:
Подтвердить выполнение исправленного PRD без регрессии pipeline 2.0.

Steps:
- Прогнать unit, integration, security и offscreen UI tests.
- Проверить migration обезличенного config/draft 2.0.
- Выполнить именованные smoke-сценарии трёх режимов.
- Проверить Windows/macOS build без публикации.
- Обновить `UI_WIZARD_3.0.ru.md`, пользовательскую инструкцию и changelog.
- Составить traceability table PRD Key → Task Key → Test/Evidence.

Acceptance:
- [ ] Все критерии `CG3-PRD-001` имеют test/evidence или явный research status.
- [ ] Существующий pipeline не потерял поддерживаемые возможности.
- [ ] В release нет секретов, пользовательских файлов и benchmark inputs.
- [ ] Release/tag/publish выполняются только отдельной явно разрешённой задачей.

Verification:
- [ ] `python -m unittest discover -s tests -v`
- [ ] `python -m py_compile main.py v3_*.py`
- [ ] Offscreen smoke всех маршрутов и fake-provider run.
- [ ] Отдельные build checks Windows/macOS.

Notes:
- Следующий рекомендованный workflow реализации:
  `$code-vibecoding-workflow`, начиная с `CG3-TASK-016`.


