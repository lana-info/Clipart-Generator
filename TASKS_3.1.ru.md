# Задачи Vibix Images 3.1.0

Основание: `PRD_3.1.ru.md`
Task Set Key: `CG31-TASKSET-001`
База: завершённая версия 3.0.7 (`78f8c63`)

## Порядок выполнения

Сначала фиксируются release/branch boundaries и общие UI contracts, затем
реализуются независимые вертикальные slices. После каждых двух-трёх задач
выполняется checkpoint. Ни один paid smoke или build не запускается без
отдельной команды владельца.

## Обязательный visual gate для каждой UI-задачи

До source edits для Tasks 1–7 и 10–12, а также для любой другой задачи,
которая затронет видимый интерфейс:

- [ ] Простыми словами подтверждены цель, пользовательское действие, scope и
  неизменяемые части текущего экрана.
- [ ] Показан visual mockup в полном контексте приложения, включая 1120×780 и
  пригодность при 980×700.
- [ ] Показаны applicable states: default/empty, populated/enabled,
  provider/model variants, validation/error и hidden/disabled.
- [ ] Для существующего экрана показано сравнение `Сейчас` / `Предлагается`.
- [ ] Владелец явно написал `Макет утверждён`; общее утверждение PRD не заменяет
  это task-specific согласование.
- [ ] Approved mockup сохранён с dummy data в `docs/ui/3.1/<task-id>/` и связан
  с task/spec; финальная версия визуально близка к ожидаемому приложению.
- [ ] После реализации real screenshots сопоставлены с approved mockup, а
  отклонения исправлены или отдельно утверждены.

Если до task-specific approval обнаруживается новый визуальный вопрос, сначала
обновляется макет. Реализация не начинается параллельно с его обсуждением.

## Task 1: Разделить provider и model генерации

Status: Todo

Goal:
Показывать сначала провайдера, затем только его совместимые модели.

Steps:
- Добавить отдельные selectors `Провайдер` → `Модель` для ordinary и reference
  lanes; скрывать неактивную lane.
- Фильтровать по operation, references и capability registry.
- Мигрировать сохранённый model ID без потери поддерживаемого выбора.

Acceptance:
- [ ] В UI нет смешанного списка безымянных моделей разных providers, а mixed
  batch сохраняет независимый совместимый выбор обеих lanes.
- [ ] Несовместимая модель не попадает в run plan.
- [ ] Старые 3.0.7 drafts открываются безопасно.

Verification:
- [ ] Unit tests mapping/migration.
- [ ] Offscreen Clipart/Pinterest smoke с references и без них.

Dependencies: None. Scope: M. Requirements: `CG31-FR-001`.

## Task 2: Перестроить общий processing editor

Status: Todo

Goal:
Показывать настройки включённых этапов отдельными лёгкими секциями в порядке
фактического pipeline.

Steps:
- Оставить сверху компактный operation checklist.
- Рендерить ниже только enabled stages с heading/divider/spacing.
- Использовать один editor/recipe/builder в Clipart и Processing.

Acceptance:
- [ ] Выключенный stage и его controls отсутствуют.
- [ ] Порядок UI совпадает с run plan.
- [ ] Нет тяжёлых вложенных frames и лишней explanatory copy.

Verification:
- [ ] Contract tests order/visibility.
- [ ] Offscreen screenshots обоих routes с одинаковым recipe.

Dependencies: shared processing contract. Scope: M. Requirements:
`CG31-FR-010`, `CG31-FR-011`.

## Task 3: Фильтровать processing controls по endpoint/model

Status: Todo

Goal:
Убрать скрытые defaults и несовместимые настройки Fal.ai/KIE.

Steps:
- Для обоих upscale показать provider, model и допустимый scale.
- Для removal строить controls из выбранного endpoint profile.
- Проверить BiRefNet, rembg, Bria, Topaz и Recraft contracts.

Acceptance:
- [ ] Fal upscale нельзя запустить без видимых model/scale.
- [ ] BiRefNet, rembg и Bria controls не видны одновременно.
- [ ] Payload содержит только поля выбранного profile.

Verification:
- [ ] Parameterized registry/payload tests.
- [ ] Offscreen visibility matrix двух upscale и removal stages.

Dependencies: Task 2. Scope: M. Requirements: `CG31-FR-012`.

## Checkpoint A: Базовый UI contract

- [ ] Tasks 1–3 focused suites проходят.
- [ ] Clipart и Processing строят одинаковый порядок без stale controls.
- [ ] Diff/review не выявляет provider payload regression.

## Task 4: Исправить cleanup, 300 DPI и chroma presets

Status: Todo

Goal:
Закрепить короткие подписи и один безопасный набор key colors.

Steps:
- Оставить раздел `Очистка` с двумя утверждёнными действиями без абзацев.
- Вернуть `Установить 300 DPI` во все applicable routes.
- Удалить custom/HEX/eyedropper; оставить pure blue/green/red в общем enum.

Acceptance:
- [ ] Нет обещания удалить скрытый SynthID.
- [ ] Exact actions: `Удалить служебные данные изображения` и
  `Удалить водяной знак Gemini`.
- [ ] 300 DPI меняет metadata и не скрыт в applicable workflow.
- [ ] Prompt/removal используют один закрытый набор трёх цветов.

Verification:
- [ ] UI string/visibility tests.
- [ ] DPI metadata round-trip и draft migration tests.

Dependencies: Task 2. Scope: M. Requirements: `CG31-FR-013`–`CG31-FR-015`.

## Task 5: Добавить chroma modifier к созданию Clipart prompt

Status: Todo

Goal:
Добавлять утверждённый chroma block к series и ready prompt без изменения
исходного текста.

Steps:
- Разместить общий control и утверждённый compact helper в series и ready
  multiline prompt. CSV оставляет текст строк неизменным при импорте.
- Сразу после цветовых buttons разместить multi-select материалов и деталей;
  helper справа содержит только порядок выбора blue/red/green и короткое
  пояснение про автоматические material clauses.
- Записывать modifier/color в metadata каждого создаваемого `PromptEntry` и
  показывать final preview.
- Обновлять существующий block при смене цвета без duplicate.
- Массовое Chroma Key-применение к импортированным строкам — отдельное действие
  следующего экрана review, не часть CSV import.

Acceptance:
- [ ] Modifier off by default, существует только в Clipart и допускает разные
  colors у entries одной batch.
- [ ] Blue/red/green templates используют правильные name/HEX.
- [ ] `Акварель`, `Тонкие листья`, `Хвоя`, `Металл`, `Лента / сатин`,
  `Прозрачные детали`, `Снег / лёд` добавляют только свои clauses; отсутствие
  выбора даёт base chroma block.
- [ ] Helper compact, не повторяет selectors и не содержит технических
  объяснений. Approved visual: `docs/ui/3.1/task-5-chroma-advisor/approved-mockup.png`.
- [ ] CSV/Pinterest/Processing prompt UI не получает control.

Verification:
- [ ] Render/update/no-duplicate unit tests.
- [ ] Offscreen tests двух источников и трёх исключённых modes.

Dependencies: Task 4. Scope: M. Requirements: `CG31-FR-002`–`CG31-FR-006`.

## Task 6: Разделить `rough` и `output` и нормализовать имена

Status: Todo

Goal:
Хранить intermediates отдельно от готовых файлов с короткими говорящими names.

Steps:
- Считать выбранный путь workspace root и создавать внутри `rough/`, `output/`
  и transient hidden `.run/`; мигрировать literal legacy `output` path в parent.
- Для другого legacy path требовать одноразовый выбор workspace root до смены
  фактического output location; не продолжать молча.
- Очищать `.run/` best-effort после terminal run; persistent `rough/` не удалять
  без отдельного пользовательского действия.
- Использовать один suffix последнего stage и различать
  `_upscaled-before-2x`/`_upscaled-after-2x`.
- Нормализовать source/structured/free-form/CSV stem и collision numbering.

Acceptance:
- [ ] В `output/` нет intermediates, в `rough/` нет final `_ready`.
- [ ] `.run/` не показывается как пользовательский intermediate, а legacy path
  не создаёт молча `output/output`.
- [ ] Нет timestamp/UUID/цепочек suffix и silent overwrite.
- [ ] Пользователь не вводит имя вручную.

Verification:
- [ ] Clipart, Pinterest prompt-only и Processing integration tests всех
  применимых suffix/collisions/workspace paths.
- [ ] Windows-safe path/name tests.

Dependencies: None. Scope: M. Requirements: `CG31-FR-020`–`CG31-FR-022`.

## Checkpoint B: Основной workflow

- [ ] Tasks 4–6 tests проходят вместе с Tasks 1–3.
- [ ] Existing drafts мигрируют без custom chroma leakage.
- [ ] Run plan и фактические output paths совпадают.

## Task 7: Сделать mask editor отдельным рабочим пространством

Status: Todo — reuse existing mask/preview primitives; текущий скрытый
Results-блок не считается принятой UX-реализацией

Goal:
Открывать один result на крупном canvas с предсказуемой кистью и zoom.

Steps:
- Добавить отдельную страницу `Проверка прозрачности` с file list слева и
  large canvas справа; double click выбирает файл и фокусирует canvas.
- Реализовать Fit/25/50/100/200%, manual zoom и pan.
- Добавить visible footprint, radius, hardness, continuous stroke, add/remove,
  undo/redo и reset.
- Сохранять corrected `_ready` PNG в `output/`, alpha-mask `_alpha-mask` в
  `rough/`, atomically и без paid remover.

Acceptance:
- [ ] Полное изображение видно и масштабируется без обрезанной полосы.
- [ ] Drag рисует continuous line, cursor outline совпадает с footprint.
- [ ] File switch изолирует mask/history; preview background не сохраняется.

Verification:
- [ ] Unit tests interpolation, hardness, history и mask isolation.
- [ ] Offscreen interaction smoke и manual Windows mouse/pen acceptance.

Dependencies: Task 6, existing `background_mask.py`, `v3_transparency_preview.py`.
Scope: M. Requirements: `CG31-FR-030`–`CG31-FR-033`.

## Task 8: Зафиксировать chroma benchmark и критерии продолжения

Status: Todo

Goal:
До нового алгоритма определить собственный reproducible golden set и измеримые
критерии качества.

Steps:
- Собрать clean edge, watercolor, thin lines, foliage/openings, partial alpha и
  spill fixtures из разрешённых локальных изображений; для каждого определить
  owner pass/fail и, где есть reference mask, alpha MAE/IoU.
- Зафиксировать current RGB-distance baseline и expected alpha/visual checks.
- Задать memory/time ceilings на full-resolution image, максимум два bounded
  improvement cycles и stop/continue decision.

Acceptance:
- [ ] Каждый case имеет input, expected risk и checkerboard/black/white/bright
  comparison.
- [ ] Provenance честно фиксирует, что Clipbrook source ранее изучался как
  research reference; его code/constants/tests не входят в fixtures/spec.
- [ ] Spec может использовать изученные методы и идеи как research input, но
  не содержит скопированный code/tests/constants Clipbrook.

Verification:
- [ ] Deterministic benchmark manifest и baseline contact sheet.

Dependencies: Task 4. Scope: S. Requirements: `CG31-FR-040`–`CG31-FR-043`.

## Task 9: Реализовать собственный automatic chroma engine

Status: Todo

Goal:
Заменить RGB-distance собственным алгоритмом, выбранным по Task 8.

Steps:
- Исследовать первичные источники по matting/compositing и выбрать минимальную
  архитектуру по измеримым outcomes Task 8.
- Самостоятельно реализовать выбранные методы на Pillow/NumPy/OpenCV, при
  необходимости упростив или улучшив их под наш benchmark; не переносить
  исходные файлы, code fragments, tests или уникальные constants Clipbrook.
- Сохранить full resolution, thin details и bounded memory; неоднозначный input
  обрабатывать fail-safe с warning.

Acceptance:
- [ ] Engine заметно улучшает согласованные benchmark cases без subject damage.
- [ ] Production code использует только собственную архитектуру и существующие
  Pillow/NumPy/OpenCV.
- [ ] Failure/ambiguous key приводит к safe result/warning, не к silent damage.
- [ ] Обычный code review подтверждает, что в change set нет перенесённых
  файлов или скопированных code fragments Clipbrook.

Verification:
- [ ] Alpha/image regression metrics и contact sheet against baseline.
- [ ] Full-resolution performance/memory test.

Dependencies: Task 8. Scope: M на один bounded prototype cycle; если выбранная
архитектура требует больше пяти файлов, до coding разбить реализацию ещё раз.
Requirements:
`CG31-FR-040`, `CG31-FR-042`, `CG31-FR-043`.

## Task 10: Интегрировать automatic chroma UX

Status: Todo

Goal:
Сделать `Автоматически` основным понятным режимом без обязательных tolerance и
softness.

Steps:
- Подключить engine к common provider/recipe/run plan.
- Скрыть numeric parameters из basic UI.
- Добавить simple edge profiles только если Task 8/9 benchmark докажет пользу.

Acceptance:
- [ ] Default run не требует понимания tolerance/softness.
- [ ] Prompt key color и removal key registry не расходятся.
- [ ] Existing drafts мигрируют в safe automatic/default behavior.

Verification:
- [ ] Unit/UI/worker integration tests и manual Windows series smoke.

Dependencies: Tasks 5, 7, 9. Scope: M. Requirements: `CG31-FR-041`.

## Checkpoint C: Alpha quality

- [ ] Tasks 7–10 проходят golden benchmark и full offline regression.
- [ ] Owner accepts representative failures/successes on target Windows UI.
- [ ] Continue decision записан; при stop engine не включается молча.

## Task 11: Добавить массовое редактирование prompt

Status: Todo

Goal:
Безопасно менять выделенные строки или весь список одной reversible operation.

Steps:
- Добавить find/replace, insert-after, prepend и append.
- Показывать scope/count/preview и no-match rows.
- Менять только user-authored text: не редактировать и не дублировать system
  chroma metadata/rendered block. Сохранять references/order и undo одной batch
  operation.

Acceptance:
- [ ] Работает произвольный selection, включая 15 строк, и весь список.
- [ ] No-match не меняет строку и виден до подтверждения.
- [ ] References/order остаются неизменными.

Verification:
- [ ] Unit tests каждой операции, Unicode, selection/all/no-match/undo.
- [ ] Offscreen performance smoke на сотнях строк.

Dependencies: Task 5 and shared prompt workspace. Scope: M. Requirements:
`CG31-FR-004`.

## Task 12: Добавить безопасный Fal.ai concurrency

Status: Todo — Fal connection/key/balance already verified; implement approved
1/2/3 selector with default 3. KIE/PhotoRoom already covered

Goal:
Расширить provider-specific scheduler без опасного общего значения `35`.

Steps:
- Не переделывать working Fal key/connection/balance checks; balance availability
  не смешивать с concurrency setting.
- Добавить Fal selector 1/2/3 с default 3 и сохранить общий remote cap 6 для
  KIE/PhotoRoom/Fal.
- Проверить 429/backoff/stop admission/per-item mapping network-free tests.

Acceptance:
- [ ] Лимит одного provider не меняет другой.
- [ ] Все операции provider делят один лимит и stop gate.
- [ ] Значение выше 3 нельзя выбрать/восстановить; default Fal равен 3.
- [ ] HTTP 429 ограниченно повторяется и не приводит к потере очереди.

Verification:
- [ ] Network-free scheduler tests для Fal 1/2/3, общего cap 6, 429 и stop.
- [ ] Paid smoke не является обязательным для completion/release и запускается
  только отдельной командой владельца.

Dependencies: existing Fal provider contract. Scope: M.
Requirements: `CG31-FR-050`, `CG31-FR-051`.

## Task 13: Интегрировать и принять 3.1.0

Status: Todo

Goal:
Интегрировать task branches по одной в `develop/3.1` и подготовить проверяемый
Windows candidate только после полной source acceptance.

Steps:
- Merge tasks in dependency order with verification after each integration.
- Run focused, full offline, compile, sensitive-artifact and diff checks.
- Провести manual Windows acceptance; build — только отдельной командой.

Acceptance:
- [ ] Все `CG31-AC-001`–`CG31-AC-009` имеют evidence.
- [ ] Для всех UI-задач выполнен `CG31-AC-010`: approved mockup существует до
  первого implementation commit, итоговые screenshots ему соответствуют.
- [ ] Release/version меняется на `3.1.0` только в release-preparation task.
- [ ] Update не публикуется автоматически.

Verification:
- [ ] History/merge-base audit, full tests and Windows checklist.

Dependencies: Tasks 1–12. Scope: M.

## Исторические задачи 3.0

`NEXT-TASK-009B` и `NEXT-TASK-009C` в `TASKS_3.0.ru.md` остаются историческим
описанием baseline 3.0.7. Для разработки 3.1 их статусы `Done/In progress`,
tolerance/softness UI и встроенный Results editor superseded Tasks 7–10 этого
файла и не являются текущими acceptance criteria.
