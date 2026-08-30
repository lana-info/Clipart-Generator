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

## Task 1: Явные selectors `provider — model` генерации

Status: Done — superseded and completed by Task 24 at `aaf6a4f`

Goal:
Показывать понятные модели с provider, не удаляя ни одной существующей модели,
и разделять настройки обычной и reference-генерации там, где их контракты
различаются.

Steps:
- Сделать каждый selector `Модель` с подписями `KIE — <нейросеть>` и
  `Fal.ai — <нейросеть>`; сохранить все model ID и существующие варианты.
- Добавить в text-to-image каталог Fal.ai модели Recraft V4, Ideogram V4 Fast,
  FLUX.2 Klein 4B, Kling O3 Image и Bria Fibo Gen 1.5. Ideogram V3 Transparent
  остаётся доступной; две модели с endpoint без префикса `fal-ai/` всё равно
  маршрутизируются через Fal.ai по явному реестру, а не по имени строки.
- Оставить общим только `Вариантов на промпт`.
- Если в batch есть референсы, показывать отдельные reference selectors модели,
  пропорции и разрешения и фильтровать каждый список по совместимости.
- Мигрировать сохранённый model ID без потери поддерживаемого выбора.

Acceptance:
- [x] В UI нет безымянных моделей: каждая подпись начинается с `KIE —` или
  `Fal.ai —`; существующие модели не удалены.
- [x] Обычные и reference prompts используют отдельные модель, пропорцию и
  разрешение; количество вариантов общее, несовместимые значения не попадают
  в run plan.
- [x] Старые 3.0.7 drafts открываются безопасно.

Verification:
- [x] Unit tests mapping/migration.
- [x] Offscreen Clipart/Pinterest smoke с references и без них.

Dependencies: None. Scope: M. Requirements: `CG31-FR-001`.

## Task 2: Перестроить общий processing editor

Status: Done in source — approved and implemented screenshots recorded;
Windows scaling remains in Task 13

Goal:
Показывать настройки включённых этапов отдельными лёгкими секциями в порядке
фактического pipeline.

Steps:
- Оставить сверху компактный operation checklist в трёх колонках, сохраняя
  установленный порядок чтения.
- Рендерить ниже только enabled stages с heading/divider/spacing.
- Показывать divider только между двумя реально включёнными stage, никогда не
  выводить пустые разделители.
- Использовать один editor/recipe/builder в Clipart и Processing.

Acceptance:
- [x] Выключенный stage и его controls отсутствуют.
- [x] Порядок UI совпадает с run plan.
- [x] Нет тяжёлых вложенных frames и лишней explanatory copy.
- [x] При одной включённой операции нет лишнего divider; при выключенной
  операции нет её пустого блока.

Verification:
- [x] Contract tests order/visibility.
- [x] Offscreen screenshots обоих routes с одинаковым recipe.

Dependencies: shared processing contract. Scope: M. Requirements:
`CG31-FR-010`, `CG31-FR-011`.

## Task 3: Фильтровать processing controls по endpoint/model

Status: Done in source — implementation checkpoint `677147d`; BiRefNet, Bria
and rembg screenshots recorded, Windows scaling remains in Task 13

Goal:
Убрать скрытые defaults и несовместимые настройки Fal.ai/KIE.

Steps:
- Для обоих upscale показать provider, model и допустимый scale.
- Для removal строить controls из выбранного endpoint profile.
- Проверить BiRefNet, rembg, Bria, Topaz и Recraft contracts.

Acceptance:
- [x] Fal upscale нельзя запустить без видимых model/scale.
- [x] BiRefNet, rembg и Bria controls не видны одновременно.
- [x] Payload содержит только поля выбранного profile.

Verification:
- [x] Parameterized registry/payload tests.
- [x] Offscreen visibility matrix двух upscale и removal stages.

Dependencies: Task 2. Scope: M. Requirements: `CG31-FR-012`.

## Checkpoint A: Базовый UI contract

- [x] Tasks 1–3 focused suites проходят.
- [x] Clipart и Processing строят одинаковый порядок без stale controls.
- [x] Diff/review не выявляет provider payload regression.

## Task 4: Исправить cleanup, 300 DPI и chroma presets

Status: Done in source — approved copy and implementation checkpoint `46f11ba`;
shared editor screenshots recorded, Windows scaling remains in Task 13

Goal:
Закрепить короткие подписи и один безопасный набор key colors.

Steps:
- Оставить раздел `Очистка` с двумя утверждёнными действиями без абзацев.
- Вернуть `Установить 300 DPI` во все applicable routes.
- Удалить custom/HEX/eyedropper; оставить pure blue/green/red в общем enum.

Acceptance:
- [x] Нет обещания удалить скрытый SynthID.
- [x] Exact actions: `Удалить служебные данные изображения` и
  `Удалить водяной знак Gemini`.
- [x] 300 DPI меняет metadata и не скрыт в applicable workflow.
- [x] Prompt/removal используют один закрытый набор трёх цветов.

Verification:
- [x] UI string/visibility tests.
- [x] DPI metadata round-trip и draft migration tests.

Dependencies: Task 2. Scope: M. Requirements: `CG31-FR-013`–`CG31-FR-015`.

## Task 5: Добавить chroma modifier к созданию Clipart prompt

Status: Source behavior fixed — prebuild audit restored the approved helper and
three visible color buttons; 980×700 responsive layout and Windows acceptance
remain open in Task 13. Linux offscreen currently measures `140 px` horizontal
overflow at 980×700, so Task 5 is not yet visually accepted at the minimum size.

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
- [x] Modifier off by default, существует только в Clipart и допускает разные
  colors у entries одной batch.
- [x] Blue/red/green templates используют правильные name/HEX.
- [x] `Акварель`, `Тонкие листья`, `Хвоя`, `Металл`, `Лента / сатин`,
  `Прозрачные детали`, `Снег / лёд` добавляют только свои clauses; отсутствие
  выбора даёт base chroma block.
- [x] Helper compact, не повторяет selectors и не содержит технических
  объяснений. Approved visual: `docs/ui/3.1/task-5-chroma-advisor/approved-mockup.png`.
- [x] Новый generator по умолчанию выбирает синий; сохранённый выбор проекта
  не перезаписывается.
- [x] Разрешены максимум три материала: выбранные тёмно-бирюзовые с белым
  текстом, остальные при достижении лимита приглушены без постоянной подписи.
- [x] CSV/Pinterest/Processing prompt UI не получает control.

Verification:
- [x] Render/update/no-duplicate unit tests.
- [x] Offscreen tests двух источников и трёх исключённых modes.

Evidence: follow-up branch `codex/fix-3.1-chroma-control-ux`; focused offscreen
tests generator/paste и prompt-state проходят. Visual screenshot сопоставлен с
утверждённым compact layout; лимит сериализуется, поэтому старый draft с
лишними materials безопасно сохраняет первые три.

Follow-up 2026-08-30: clause `Прозрачные детали` отдельно усиливается на ветке
`codex/fix-3.1-transparent-material-prompt`. Он требует genuine partial opacity,
видимость предмета или того же chroma-фона сквозь весь материал и запрещает
непрозрачную pastel/key-coloured имитацию прозрачности. Focused prompt suite:
119 tests и 16 subtests проходят; остальные material clauses не меняются.

Dependencies: Task 4. Scope: M. Requirements: `CG31-FR-002`–`CG31-FR-006`.

## Task 6: Разделить `rough` и `output` и нормализовать имена

Status: Done in source — implementation checkpoints `ec31203`, `ba95ba0`,
`99ea7eb`, `6551011`; manual Windows path/output acceptance remains in Task 13

Goal:
Хранить intermediates отдельно от готовых файлов с короткими говорящими names.

Steps:
- Считать выбранный путь workspace root и создавать внутри `rough/`, `output/`
  и transient hidden `.run/`; мигрировать literal legacy `output` path в parent.
- Не добавлять миграционную страницу: любой другой сохранённый путь продолжает
  использоваться как workspace root без изменения привычного алгоритма.
- Очищать `.run/` best-effort после terminal run; persistent `rough/` не удалять
  без отдельного пользовательского действия.
- Использовать один suffix последнего stage и различать
  `_upscaled-before-2x`/`_upscaled-after-2x`.
- Нормализовать source/structured/free-form/CSV stem и collision numbering.
  Для structured prompt имя берётся из значения `Object`/`Объект`, без слов
  `object`/`scene`; известные русские названия клипартов получают короткий
  английский эквивалент (`лисенок` → `fox`).

Acceptance:
- [x] В `output/` нет intermediates, в `rough/` нет final `_ready`.
- [x] `.run/` не показывается как пользовательский intermediate, literal legacy
  `output` path автоматически нормализуется в parent и не создаёт
  `output/output`; дополнительной страницы нет.
- [x] Нет timestamp/UUID/цепочек suffix и silent overwrite.
- [x] Пользователь не вводит имя вручную.
- [x] Generated output не содержит служебных label `object`/`scene`: например,
  `Object: fox. Scene: …` сохраняется как `fox_01_ready.png`.

Verification:
- [x] Clipart, Pinterest prompt-only и Processing integration tests всех
  применимых suffix/collisions/workspace paths.
- [x] Windows-safe path/name tests.

Dependencies: None. Scope: M. Requirements: `CG31-FR-020`–`CG31-FR-022`.

## Checkpoint B: Основной workflow

- [x] Tasks 4–6 tests проходят вместе с Tasks 1–3.
- [x] Existing drafts мигрируют без custom chroma leakage.
- [x] Run plan и фактические output paths совпадают.

## Task 7: Сделать mask editor отдельным рабочим пространством

Status: In progress — visual approved; implementation checkpoints `1724c76`,
`35931e3`; manual Windows mouse/pen acceptance pending

Goal:
Открывать один result на крупном canvas с предсказуемой кистью и zoom.

Steps:
- Добавить отдельную страницу `Проверка и корректировка прозрачности` с large
  canvas слева и прокручиваемым file list/инструментами в компактной правой
  панели; на Results дать кнопку `Проверить прозрачность`, double click оставить
  shortcut.
- Реализовать Fit/50/100/150/200/300%, полноэкранный canvas и pan удержанием
  `Пробел` без отдельного переключателя инструмента; во время удержания
  показывать только иконку ладони.
- Добавить visible footprint, radius, hardness, continuous stroke, add/remove,
  undo/redo и reset; максимальный radius кисти — 200 px.
- Сохранять corrected `_ready` PNG в `output/`, alpha-mask `_alpha-mask` в
  `rough/` согласованной парой с rollback при ошибке, без paid remover и без
  потери 300 DPI.

Acceptance:
- [x] Полное изображение видно и масштабируется без обрезанной полосы.
- [x] Drag рисует continuous line, cursor outline совпадает с footprint.
- [x] File switch изолирует mask; preview background не сохраняется, а
  несохранённые изменения не теряются без предупреждения.
- [x] `Сохранить PNG` — единственное primary action; `К результатам` — secondary.
- [x] Пробел срабатывает и после фокуса на панели инструментов, а не только
  после клика по canvas.
- [x] Доступны только утверждённые presets `Fit`, `50%`, `100%`, `150%`,
  `200%`, `300%`; выбранный масштаб сохраняется при переключении файлов.

Verification:
- [x] Unit tests interpolation, hardness, bounded history, mask isolation,
  300-DPI round-trip и rollback парного сохранения.
- [x] Offscreen interaction smoke и screenshot при 980×700.
- [ ] Manual Windows mouse/pen acceptance.

Implementation evidence: feature commit `1724c76`; 83 focused offscreen tests,
`py_compile` и `git diff --check` прошли. Замер одного движения кисти на 4K —
около 0,018 с вместо 3,22 с до оптимизации. При возврате к файлу его текущая
несохранённая маска восстанавливается, но отдельная Undo/Redo history для ранее
покинутого файла не сохраняется.

Dependencies: Task 6, existing `background_mask.py`, `v3_transparency_preview.py`.
Scope: M. Requirements: `CG31-FR-030`–`CG31-FR-033`.

## Task 8: Зафиксировать chroma benchmark и критерии продолжения

Status: Done (VDS checkpoint; Windows performance повторяется при acceptance)

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
- [x] Каждый case имеет input, expected risk и checkerboard/black/white/bright
  comparison.
- [x] Provenance честно фиксирует, что Clipbrook source ранее изучался как
  research reference; его code/constants/tests не входят в fixtures/spec.
- [x] Spec может использовать изученные методы и идеи как research input, но
  не содержит скопированный code/tests/constants Clipbrook.

Verification:
- [x] Deterministic benchmark manifest и baseline contact sheet.

Implementation evidence: feature commits `063a7cd` и `ed0dc4d`; manifest
содержит шесть детерминированных cases и hash-checked input/mask/foreground
goldens. Канонический offline baseline создан чистым commit `063a7cd`: mean
alpha MAE `0.04016`, alpha IoU `0.92349`, median 2048×2048 runtime `2.606 s`,
peak RSS `303.805 MiB`. 19 focused tests, `py_compile` и `git diff --check`
прошли. Обычный runner не изменяет goldens; их обновление вынесено в отдельную
явно подтверждаемую команду. Candidate comparison отклоняет другой schema,
fixture/performance size, kind/key color и подменённую summary.

Dependencies: Task 4. Scope: S. Requirements: `CG31-FR-040`–`CG31-FR-043`.

## Task 9: Реализовать собственный automatic chroma engine

Status: Done (quality follow-up verified on owner series; Windows acceptance pending)

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
- [x] Engine заметно улучшает согласованные benchmark cases без subject damage.
- [x] Production code использует только собственную архитектуру и существующие
  Pillow/NumPy/OpenCV.
- [x] Failure/ambiguous key приводит к safe result/warning, не к silent damage.
- [x] Обычный code review подтверждает, что в change set нет перенесённых
  файлов или скопированных code fragments Clipbrook.

Verification:
- [x] Alpha/image regression metrics и contact sheet against baseline.
- [x] Full-resolution performance/memory test.

Implementation evidence: feature commits `07f84a7` и `59df0e1`; accepted
automatic-v1 report создан из clean commit `07f84a7` (`git_dirty=false`). Mean
alpha MAE улучшен на `54.7%`, улучшены `5/6` cases, alpha IoU `0.96870`, median
runtime 2048×2048 `0.758 s`, peak RSS `421.055 MiB` при owner-approved ceiling
`448 MiB`. 34 focused tests, `py_compile`, `git diff --check` и три независимых
review pass завершены; blocking/important findings закрыты. Неоднородный фон,
неверный key, заметные near-key детали предмета и чрезмерная фрагментация
отклоняются до изменения файла. Exact selected-key pixels по контракту считаются
фоном/openings; если предмет содержит этот точный цвет, пользователь выбирает
другой preset. Canonical report и contact sheet находятся в
`benchmarks/chroma/automatic-v1/`.

Контрольная генерация настоящей полупрозрачной
тюлевой юбки показала, что улучшенный prompt создаёт пригодный measurable
input и выявляет жёлто-зелёные пятна прежней candidate-реализации Vibix внутри
ткани. Clipbrook на том же input сильнее прореживает сетку. Отдельная
bounded-задача после prompt change закрыта через реконструкцию только цвета в
genuine translucent interior без потери mesh, лап, хвоста и обычных краёв.
Presets и новые UI-controls для этого не добавлялись.

Quality follow-up 2026-08-30: восемь исходных 2048×2048 PNG владельца выявили
пробел синтетического benchmark — генераторы отдают не математически чистый
key, а насыщенный оттенок вроде `#087CF3`. Старый staged de-spill вычитал key
channel слишком агрессивно и добавлял два остальных канала, создавая жёлтый
контур; alpha также теряла часть различимой полупрозрачной кромки. Исправленный
движок измеряет фактический border key, выбирает единый detailed path для
окрашенного rendered key, использует полный RGB-образец с нескольких глубин
предмета, восстанавливает смесь с сохранением яркости и отдельно решает первый
пограничный ряд. На увеличенных black/white comparisons всех восьми файлов
жёлтый ореол исчез, шерсть, лапы, юбки и иголки сохраняются не хуже Clipbrook;
на детерминированном rendered-key regression с blue/green/red средняя ошибка
RGB кромки не превышает `18/255`, complementary bias — `12/255`, а потеря
различимой кромки ограничена 64 пикселями. Изолированный PNG 2048×2048
использует `420.9 MiB`, оставаясь ниже ceiling `448 MiB`. Пользовательские
изображения и исследовательские outputs остаются локальными и в git не входят.
Full offline suite: 980 passed, 55 intentional skips, 3 deselected и 130
subtests. Третье исключение — уже существующий stale route-test Processing,
который ожидает отсутствие ранее утверждённого экрана Transparency; на чистом
`develop/3.1` он падает так же и исправляется отдельной задачей.

Дополнительная проверка полупрозрачной юбки выявила второй частный случай:
staged de-spill мог слишком сильно вычесть канал фона не только из обычной
полупрозрачной сетки, но и из локальных непрозрачных точек внутри неё. Из-за
этого появлялись жёлто-оливковые островки, хотя сама alpha-маска сохраняла
ткань лучше Clipbrook. Исправление меняет только цвет в окрестности широкой
полупрозрачной области, не изменяет alpha и не затрагивает обычные мягкие края.
Детерминированный regression покрывает blue/green/red; полный offline suite:
981 passed, 55 intentional skips, 3 deselected и 133 subtests. Automatic
benchmark 2048×2048: median `1.373 s`, peak RSS `421.402 MiB` при ceiling
`448 MiB`. На увеличенном сравнении нижняя кромка юбки сохраняется непрерывнее
старого Vibix и Clipbrook; окончательный Windows smoke на других реальных
полупрозрачных материалах остаётся обязательным.

Dependencies: Task 8. Scope: M на один bounded prototype cycle; если выбранная
архитектура требует больше пяти файлов, до coding разбить реализацию ещё раз.
Requirements:
`CG31-FR-040`, `CG31-FR-042`, `CG31-FR-043`.

## Task 10: Интегрировать automatic chroma UX

Status: Done (VDS checkpoint; Windows series smoke pending)

Goal:
Сделать `Автоматически` основным понятным режимом без обязательных tolerance и
softness.

Steps:
- Подключить engine к common provider/recipe/run plan.
- Скрыть numeric parameters из basic UI.
- Добавить simple edge profiles только если Task 8/9 benchmark докажет пользу.

Acceptance:
- [x] Default run не требует понимания tolerance/softness.
- [x] Prompt key color и removal key registry не расходятся.
- [x] Existing drafts мигрируют в safe automatic/default behavior.

Verification:
- [x] Unit/UI/worker integration tests.
- [ ] Manual Windows series smoke.

Implementation evidence: feature commit `33d2544`. Common Clipart/Processing
run plan передаёт automatic worker только preset `chroma_key_color`; custom,
tolerance и softness остаются лишь legacy draft fields и не попадают в run.
Worker также нормализует прямой legacy custom/HEX/unknown input в safe `blue`.
Все prompt/removal selectors используют один registry `blue/red/green`,
производный от engine `KEY_COLORS`. Simple edge profiles не добавлены: Task 8/9
не доказали отдельную измеримую пользу профилей. 162 targeted tests,
`py_compile`, offscreen UI smoke, `git diff --check` и независимый review прошли.
Четыре старых output-layout failure воспроизводятся на base `59df0e1` и не
относятся к Task 10; общий regression gate остаётся открытым до интеграции
веток и Windows acceptance.

Dependencies: Tasks 5, 7, 9. Scope: M. Requirements: `CG31-FR-041`.

## Checkpoint C: Alpha quality

- [ ] Tasks 7–10 проходят golden benchmark и full offline regression.
- [ ] Owner accepts representative failures/successes on target Windows UI.
- [ ] Continue decision записан; при stop engine не включается молча.

## Task 11: Добавить массовое редактирование prompt

Status: Done (Linux-safe checkpoint; Windows visual smoke remains in the final
3.1 acceptance pass)

Goal:
Безопасно менять выделенные строки или весь список одной reversible operation.

Steps:
- Добавить find/replace и короткие действия `В начало`/`В конец`; отдельную
  кнопку insert-after не показывать.
- Показывать scope/count/preview и no-match rows.
- Менять только user-authored text: не редактировать и не дублировать system
  chroma metadata/rendered block. Сохранять references/order и undo одной batch
  operation.
- Добавить в нижнюю панель проверки промптов экспорт всех строк в совместимый
  CSV с колонками `Prompt` и `References`.

Acceptance:
- [x] Работает произвольный selection, включая 15 строк, и весь список.
- [x] No-match не меняет строку и виден до подтверждения.
- [x] References/order остаются неизменными.
- [x] Экспорт CSV можно сразу импортировать обратно без потери промптов и
  референсов.

Verification:
- [x] Unit tests каждой операции, Unicode, selection/all/no-match/undo.
- [x] Offscreen performance smoke на сотнях строк.

Implementation evidence: feature commit `ef56eb6`. На странице проверки
промптов одна кнопка `Найти и заменить` открывает modal preview с действиями
`Заменить`, `В начало`, `В конец` и scope `Выбранные`/`Все`. До применения
видны количество, до трёх примеров и номера строк без совпадений; no-op
`X → X` не разрешает применение. Один undo восстанавливает весь последний
batch и сбрасывается после следующего ручного изменения. References, порядок
и сгенерированный Chroma Key suffix сохраняются. 71 focused test,
`py_compile`, `git diff --check`, offscreen screenshots и независимый review
прошли; 5000 строк обработаны за 0.013 s в локальном smoke.

Dependencies: Task 5 and shared prompt workspace. Scope: M. Requirements:
`CG31-FR-004`.

## Task 12: Добавить безопасный Fal.ai concurrency

Status: Done — implementation `40e78bc` on
`codex/feat-3.1-fal-concurrency`; Fal connection/key/balance flow unchanged

Goal:
Расширить provider-specific scheduler без опасного общего значения `35`.

Steps:
- Не переделывать working Fal key/connection/balance checks; balance availability
  не смешивать с concurrency setting.
- Добавить Fal selector 1/2/3 с default 3 и сохранить общий remote cap 6 для
  KIE/PhotoRoom/Fal.
- Проверить 429/backoff/stop admission/per-item mapping network-free tests.

Acceptance:
- [x] Лимит одного provider не меняет другой.
- [x] Все операции provider делят один лимит и stop gate.
- [x] Значение выше 3 нельзя выбрать/восстановить; default Fal равен 3.
- [x] HTTP 429 ограниченно повторяется и не приводит к потере очереди.

Verification:
- [x] Network-free scheduler tests для Fal 1/2/3, общего cap 6, 429 и stop.
- [x] Paid smoke не является обязательным для completion/release и запускается
  только отдельной командой владельца.

Evidence: 135 focused tests и 23 subtests прошли; `py_compile`,
`git diff --check`, tracked-sensitive-artifact guard и независимый review
прошли. Реальный платный вызов не выполнялся; 429/backoff/stop проверены
детерминированными network-free tests. Offscreen screenshot подтвердил
отдельную строку `Одновременных задач Fal.ai` со значением 3.

Dependencies: existing Fal provider contract. Scope: M.
Requirements: `CG31-FR-050`, `CG31-FR-051`.

## Task 14: Сохранить работу при временной недоступности лицензионного сервера

Status: Done in source — approved visual and VDS security tests pass; manual
Windows offline startup/run acceptance remains in Task 13

Goal:
Не блокировать уже подтверждённого пользователя из-за краткого сбоя сервера или
сети, сохраняя ограниченную и проверяемую лицензионную границу.

Steps:
- До source/UI работы согласовать точный offline grace period (рекомендуется 7
  календарных дней) и простой текст статуса; для нового либо заметно
  переработанного окна сначала подготовить visual mockup по `CG31-UX-001`–`007`.
- После успешной signed online authorization атомарно сохранять только нужные
  проверяемые данные: подписанное подтверждение, device binding, время
  последней проверки и защищённый маркер времени. Лицензионный ключ не хранить
  и не показывать.
- При transport/server outage использовать grace только для ранее
  подтверждённого состояния; явно отклонённая, отозванная, истёкшая,
  повреждённая или новая лицензия не получает offline-доступ.
- Защититься от expiry, clock rollback и повреждения состояния; после grace
  остановить новые операции с понятной возможностью повторить проверку.

Acceptance:
- [x] Уже подтверждённая лицензия работает при timeout/5xx внутри утверждённого
  grace и показывает дату последней успешной проверки.
- [x] Первая активация, 401/403/явный отказ, подписанный ответ, уже истёкший в
  момент получения, повреждённое состояние, clock rollback и grace expiry не
  дают offline-доступ.
- [x] Сбой сервера не маскируется как новая успешная активация; ключ лицензии не
  попадает в state, UI или diagnostic journal.

Verification:
- [x] Network-free tests: valid grace, expiry, timeout/5xx, explicit denial,
  expired signed payload, state tampering и clock rollback.
- [ ] Manual offline startup/run acceptance с заранее активированной тестовой
  лицензией; отдельная проверка первого запуска без сети.

Evidence: offline grace равен семи календарным дням и включается только после
`LicenseUnavailableError`. Cache атомарно хранит исходный server-signed envelope,
device/nonce binding и подписанный device key маркер времени; обе подписи
перепроверяются перед каждым offline run. Явные HTTP 400/401/403/409/422,
повреждение, подмена server envelope, rollback времени и окончание grace
остаются fail-closed. Approved и implemented screenshots сохранены в
`docs/ui/3.1/task-14-license-grace/`. 57 focused license/update/release tests и
полный offline suite (950 passed, 56 intentional skips, 2 deselected, 127
subtests) проходят; `py_compile` и sensitive-artifact scan также проходят,
лицензионный ключ в state/UI/diagnostics не добавлен.

Dependencies: existing signed license client and startup gate. Scope: M.
Requirements: `CG31-FR-060`–`CG31-FR-062`.

## Task 15: Показать описание изменений при обновлении

Status: Done — visual approved 2026-08-29; integrated in `develop/3.1` at
`ea57e12`

Goal:
Показывать пользователю краткое описание изменений новой версии до решения о
скачивании, используя уже подписанные данные release manifest.

Acceptance:
- [x] При непустом `notes` диалог показывает «Что нового» и сам текст до
  действий «Не сейчас» / «Обновить».
- [x] Текст отображается как plain text, без исполнения HTML/разметки.
- [x] При пустом `notes` блок не занимает место; длинное описание прокручивается
  в компактной области.

Verification:
- [x] Offscreen tests: обычное описание, пустое описание и текст с HTML-маркерами.
- [x] Approved и implemented screenshots сохранены в
  `docs/ui/3.1/task-15-update-notes/`.

Evidence: поле `notes` уже приходит в server-signed manifest и ограничено 2000
символами в `UpdateClient`; UI не создаёт нового сетевого запроса и не меняет
сценарий согласия, скачивания либо проверки SHA-256.

Dependencies: existing V3 signed update client. Scope: S.

## Task 22: Упростить Pinterest prompt и выбор генерации

Status: Done — integrated in `develop/3.1` at `f00cec4`

Goal:
Убрать из Pinterest не относящийся к нему Chroma Key-helper и сделать выбор
text/reference generation понятным без технических описаний.

Acceptance:

- [x] На Pinterest-странице готового промпта отсутствует весь Chroma Key-блок;
  референсы, CSV и добавление промпта не меняются.
- [x] Pinterest показывает отдельную обычную модель и, только при наличии
  референсов, отдельную модель с референсом. Отдельные пропорции и разрешения
  для обоих маршрутов добавлены Task 24; число вариантов остаётся общим.
- [x] Нет раскрывающегося блока, описаний «защищённой серии/слоя» и фиксированных
  пиксельных пояснений.
- [x] Наглядное превью выбранной пропорции работает одинаково в Pinterest и
  Clipart.

Verification:

- [x] Active prompt-only offscreen tests: удаление Chroma Key controls,
  conditional reference model и ratio preview.
- [x] Existing Clipart/Pinterest focused suite, `py_compile` и `git diff --check`.

Design: `docs/ui/3.1/task-22-pinterest-prompt-no-chroma/`.

## Task 23: Проверка и корректировка прозрачности после обработки файлов

Status: Done — integrated in `develop/3.1` at `ea08918`

Goal:
После обычной обработки файлов открывать тот же утверждённый редактор
прозрачности, что и в режиме Clipart.

Acceptance:

- [x] На результатах обработки успешный PNG можно открыть кнопкой и двойным
  кликом в отдельном редакторе прозрачности.
- [x] Редактор показывает только успешные файлы текущего запуска, открывает
  выбранный файл и возвращает пользователя к результатам.
- [x] Черновик, сохранённый на странице редактора, при повторном открытии
  переходит к устойчивой странице результатов, так как очередь запуска не
  сохраняется в проекте.
- [x] Внешний вид не менялся: повторно используется утверждённый Clipart
  editor, включая кисть, pan пробелом, масштаб и экспорт PNG.

Verification:

- [x] Focused offscreen tests `tests.test_v3_run_queue` и
  `tests.test_v3_processing_flow` (75 tests).
- [x] `py_compile`, `git diff --check` и tracked sensitive-artifact scan.

## Task 24: Раздельные профили генерации для обычных и reference-промптов

Status: Done — integrated in `develop/3.1` at `aaf6a4f`

Goal:
Не допускать ошибок совместимости, когда обычная и reference-модели имеют
разные допустимые пропорции или разрешения.

Acceptance:

- [x] В Clipart и Pinterest обычные промпты используют строки «Модель»,
  «Пропорция», «Разрешение»; при наличии хотя бы одного референса появляются
  отдельные строки для референсной модели, пропорции и разрешения.
- [x] Каждый список вариантов берётся из контракта именно выбранной модели и
  своего типа генерации; недоступные варианты не предлагаются.
- [x] Количество вариантов остаётся общим для серии.
- [x] Референсные строки действительно получают свой профиль в worker,
  валидации, расчёте стоимости и Fal.ai quantity estimate, а не только в UI.
- [x] Нет раскрывающегося технического блока: reference-поля показываются
  напрямую и только при наличии референсов.

Verification:

- [x] Active offscreen Clipart/Pinterest tests: profile controls, маршрутизация
  профиля и расчёт стоимости для смешанной серии.
- [x] Focused suite `tests.test_v3_clipart_flow`, `tests.test_v3_pinterest_flow`
  и `tests.test_v3_run_queue` (185 tests; 54 deferred skips).
- [x] `py_compile`, `git diff --check` и tracked sensitive-artifact scan.

## Task 25: Упростить проверку и запуск Fal.ai

Status: Done — integrated in `develop/3.1` at `bdf6823`

Goal:
Не требовать подтверждения цены для запуска и не показывать предупреждение о
ключе Fal.ai, когда ключ уже задан.

Acceptance:

- [x] Нет галочки подтверждения цены и цена не блокирует запуск.
- [x] «Обновить оценку Fal.ai» показывается только для Fal.ai и располагается
  рядом со строкой стоимости; нажатие остаётся необязательным.
- [x] Не передаётся устаревший флаг `fal_cost_confirmed`, который мог бы
  остановить worker без действия пользователя.
- [x] При успешной preflight-проверке строка с техническим статусом ключа
  скрыта; ошибка остаётся только для действительно отсутствующего ключа.

Verification:

- [x] Focused Clipart/Pinterest/Fal suites (165 tests; 54 deferred skips).
- [x] `py_compile`, `git diff --check` и tracked sensitive-artifact scan.

## Task 26: Закрыть техническое ревью source checkpoint

Status: Done — integrated into `develop/3.1` by fast-forward through `c40bbdb`;
Windows acceptance remains under Task 13

Goal:
Проверить замечания к checkpoint `879d746` воспроизводимыми тестами и закрыть
подтверждённые корневые причины без архитектурной переделки.

Acceptance:
- [x] Fal key переживает restart; Fal/KIE journal синхронизирован между
  workers, сохраняет pending task IDs и продолжает их polling без повторного
  paid POST для того же входа. Fingerprint локальных KIE upload не зависит от
  временного URL, а journal защищён между процессами. Redirect не переносит
  Authorization на другой host или downgrade.
- [x] Каждый запуск изолирован в `.run/<run-id>`, резервирует имена всего batch
  и публикует только свои файлы. Прежний выбор workspace с `rough/` и `output/`
  сохранён без миграционного экрана; literal `output` нормализуется в parent.
- [x] Adversarial Chroma test подтвердил потерю enclosed near-key детали;
  automatic mode теперь останавливается с понятной ошибкой вместо стирающего
  fallback. Правило exact selected key не менялось.
- [x] Редактор ограничен 40 Мп, `QThread.finished` больше не подменён строковым
  business-сигналом, а проверка прозрачности видна также в Processing.
- [x] Installer повторно проверяется перед launch, license outage отделён от
  permanent 4xx denial, CSV атомарен, delegated update `kid` сохранён верно,
  output filename ограничен безопасным Windows budget. На Windows installer
  удерживается от записи/переименования от проверки до launch. PNG/mask
  pair-транзакция восстанавливается также после остановки процесса.

Verification:
- [x] Focused paid-task/workspace gate: 213 tests and 22 subtests.
- [x] Focused gates блоков: 269 tests + 47 subtests для Chroma/UI и 110 tests +
  18 subtests для release safety.
- [x] Final high-risk focused suite: 225 tests and 36 subtests.
- [x] Full offline suite: 1021 passed, 55 intentional skips, 2 deselected,
  140 subtests.
- [x] Все tracked Python files компилируются; sensitive-artifact scan и
  `git diff --check` проходят.
- [x] Automatic Chroma benchmark: 6 cases, 2048×2048 median `1.228 s`, peak RSS
  `421.848 MiB`; все quality gates проходят при ceiling `448 MiB`.
- [x] Повторное независимое ревью: `pass-with-nits`, новых blocking/important
  дефектов после follow-up исправлений не найдено.
- [ ] Manual Windows acceptance и replacement installer — только после
  отдельного разрешения владельца.

Requirements: `CG31-FR-020`, `022`, `030`, `052`, `053`, `061`, `070`, `071`.

## Task 13: Интегрировать и принять 3.1.0

Status: In progress — technical-review fixes are integrated into
`develop/3.1`; replacement Windows candidate remains before
acceptance/publication

Goal:
Интегрировать task branches по одной в `develop/3.1` и подготовить проверяемый
Windows candidate только после полной source acceptance.

Steps:
- [x] Merge tasks in dependency order with verification after integration.
- [x] Run focused, full offline, compile, sensitive-artifact and diff checks.
- Провести manual Windows acceptance; build — только отдельной командой.
- [ ] До build открыть интегрированный source на Windows при 1120×780 и
  980×700: сравнить Tasks 2, 3 и 5 с сохранёнными implemented screenshots,
  проверить 100%/125% scaling, отсутствие наложений и доступность навигации.
  Для Task 5 отдельно решить известный Linux-offscreen `140 px` horizontal
  overflow: явно принять прокрутку либо утвердить responsive-макет и исправить.
- [ ] Проверить мышью и пером mask editor: Fit/50/100/150/200/300%, continuous
  add/remove brush, hardness, пробел-pan, undo/redo/reset и atomic PNG/mask save.
- [ ] В новой пустой рабочей папке проверить `rough/`, `output/`, `.run/<run-id>`,
  короткие Windows-safe имена, collision numbering и отсутствие файлов
  предыдущего запуска; отдельно проверить старый сохранённый literal `output`.
- [ ] Проверить Local Chroma Key на blue/red/green, near-key деталях и нескольких
  реальных полупрозрачных материалах; exact выбранный key внутри предмета
  остаётся фоном, поэтому для такого предмета выбирается другой preset.
- [ ] С заранее активированной тестовой лицензией проверить разрешённый outage
  grace и fail-closed denial/revocation/expiry/clock rollback.
- [ ] На Windows выполнить контрольный KIE-запуск в новой пустой рабочей папке:
  один промпт, один вариант, один Task ID и ровно один ready-файл в `output/`.
  При расхождении сохранить имена файлов, SHA-256 и диагностический журнал;
  отдельно сверить ожидаемые stage-копии в `rough/`. Это paid request и требует
  отдельного явного разрешения владельца.

Acceptance:
- [ ] Все `CG31-AC-001`–`CG31-AC-009` имеют evidence.
- [ ] Для всех UI-задач выполнен `CG31-AC-010`: approved mockup существует до
  первого implementation commit, итоговые screenshots ему соответствуют.
- [ ] Release/version меняется на `3.1.0` только в release-preparation task.
- [ ] Update не публикуется автоматически.

Verification:
- [x] History/merge-base audit and full VDS tests pass.
- [x] Technical-review fix branch fast-forwarded without conflicts; merged
  offline suite: 1021 passed, 55 intentional skips, 2 deselected, 140 subtests.
- [ ] Replacement Windows candidate and manual Windows checklist remain.

Evidence: `develop/3.1` fast-forwarded from `78f8c63` through `dd01703` to
`ea57e12` without conflicts and was pushed to GitHub. Post-integration
verification: 954 passed, 56 intentional skips, 2 deselected, 127 subtests;
`py_compile` and tracked sensitive-artifact scan pass. No paid request,
installer build or publication was started.

Review checkpoint 2026-08-30: `develop/3.1` additionally merges the approved
translucent-material prompt, Processing transparency route regression and both
Chroma quality follow-ups through merge commit `554e944`. Final integrated
verification: 983 passed, 55 intentional skips, 2 configured deselections and
133 subtests. Focused Chroma/project-state checks, Python compilation,
`git diff --check` and tracked sensitive-artifact scan pass; automatic Chroma
2048×2048 peak RSS remains `421.402 MiB` under the `448 MiB` ceiling. This is a
source-review checkpoint: `release/VERSION.txt` intentionally remains `3.0.7`,
and no installer build or publication is started before the separate
review/refactoring pass.

Prebuild source-acceptance follow-up on
`codex/chore-3.1-prebuild-acceptance`: Tasks 2–6 were reconciled against code,
tests and rendered UI. Missing Task 5 helper/three color buttons and the Task 4
Gemini label mismatch were reproduced before repair. Current verification:
1026 passed, 55 intentional skips, 2 network deselections and 140 subtests;
tracked Python compilation, sensitive scan and `git diff --check` pass. Fresh
automatic Chroma metrics: alpha IoU `0.968704`, alpha MAE `0.018194`, median
2048×2048 runtime `1.357 s`, peak RSS `421.465 MiB` under `448 MiB`.

Dependencies: Tasks 1–12, 14. Scope: M.

## Исторические задачи 3.0

`NEXT-TASK-009B` и `NEXT-TASK-009C` в `TASKS_3.0.ru.md` остаются историческим
описанием baseline 3.0.7. Для разработки 3.1 их статусы `Done/In progress`,
tolerance/softness UI и встроенный Results editor superseded Tasks 7–10 этого
файла и не являются текущими acceptance criteria.
