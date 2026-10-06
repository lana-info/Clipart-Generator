# TASKS

## Режим материалов Chroma Key, 2026-10-05

- [x] Утвердить план и макет: пользователь «да, все ок»; сохранить approved/actual UI evidence.
- [x] Реализовать режим материалов в auto-clipart, processing, clipart; old API1/project compatibility.
- [x] Подключить реальный auto color и явный manual override без изменения generation record.
- [x] Проверить15 новых регрессий,167 связанных tests+5subtests; проверить3 пользовательских PNG exactRGBA и3white manual review, SHA12unchanged.
- [x] Подготовить4 подписанных module1.5.3 ZIP minCore3.2.12, verify/install4PASS,reject oldCore4PASS.
- [x] Завершить full offline-suite и финальное ревью:2770PASS/2old expectations; после их обновления affected194PASS/1skip/9subtests; финальных замечаний оппонента0.
- [x] Показать окончательный diff/проверки; пользователь2026-10-06 разрешил commit/push, Windows3.2.12/modules и временный PUBLIC→build→PRIVATE.
- [ ] После разрешённой сборки проверить installed Windows/upgrade, доставить бету и нужные модули без замены прежней беты до приёмки.

Подробности требований/рисков: STATE.md, «Режим материалов Chroma Key».


## Остаточная кайма после v16

- [x] Зафиксировать продолжение и frozenv16 snapshot.
- [ ] Проверить новый spatial texture factor на distinctknowntruth/actual.
- [x] Исследовать источник NN полосы и hiddenRGB context: newNN2 mixed result, blanketclamp отвергнут, productioncandidate не принят.
- [ ] Исправить найденную precise coverage ошибку и защитить genuine paint в spatial recovery; permanent RED до новой source правки.
- [ ] Внедрить только доказанное правило после RED, затем actual/regressions/review.

STATE.md; docs/ERRORS.md#remaining-edge-20261003.

## Исправить причины окрашивания края после диагностики

- [x] Зафиксировать permanent public regression RED до production edits:6FAIL18PASS, expectations заморожены.
- [x] Исправить ранний material prior и позднее повторное перекрашивание;30newtests GREEN, active late controls, старые negatives сохранены.
- [x] Отдельно оценить texture promotion/repair: privatepairguard отвергнут,36old/new knowntruthfails и identical-source twins записаны.
- [x] Проверить fullnative3/darkwhite/source/geometry: yellowpatch улучшен; остаточная кайма и1previousstrongpixel loss явно открыты.
- [x] Actual new localNN2 после fullnative3, finalwriter/trim/padding/DPI/receipt/profile16/API1 PASS.
- [x] Независимое ревью: latecoverageP2 закрыт6active tests+ablation; syntax/diff/sensitive checks PASS, STATE актуален. Общая visual приёмка остаётся открытой.

- [ ] Остаточный darkpoint/pinkgray edge и сильные key-hued strokes: безопасное правило не найдено; не объявлять весь край идеальным.
- [ ] InstalledWindows/newfullNN: не проверены, build не разрешён.

Разрешено владельцем после причинной диагностики. STATE.md и
docs/ERRORS.md#material-edge-fix-20261003.

## Найти причины остаточной каймы до следующей правки

- [x] Использовать systematic-debugging, заморозить product/tests и сохранить v15 evidence.
- [x] Независимо трассировать полный source до первого unmix, recovery и late repair.
- [x] Проверить local-material failure и strong shaded gap на known truth,3 key permutations, root repeat.
- [x] Разделить reference core/band/despill/finish и RGB/alpha; проверить genuine paint/additive negatives.
- [x] Проверить cached NN усиление, premult/bilinear и Qt100% без нового NN/network.
- [x] Получить независимый challenge; записать причины, границы и порядок следующей реализации.
- [ ] Исправить ранний материал и его повторное повреждение в opaque_spill; автоматическое правило ещё не доказано.
- [ ] Отдельно исправить matte promotion/late repair с сохранением настоящих opaque/key-hued линий.
- [ ] После native исправления отдельно проверить NN и итоговые actual edges; вся visual задача остаётся открытой.

Результат/требования: STATE.md. История: docs/ERRORS.md#edge-root-cause-audit-20261003.
Private итог: `../artifacts/edge-root-cause-audit-20261003/REPORT.ru.md`.

## Более чистый automatic край с разрешённой потерей слабых штрихов

- [x] Зафиксировать явное «Да» владельца и обновить границы PROJECT/STATE.
- [x] Сохранить own verifiedv14 baseline, проверить Git и чужие worktrees.
- [x] Получить независимую оценку final selection против early classifier rollback.
- [x] Проверить ограничение finalalpha<128 и source-boundary ring на actual3.
- [x] Реализовать обе automatic ветки после всех refinements, preserve suppliedalpha/legacy/core/survivorRGB.
- [x] Проверить32 mask regressions и прежнюю18+12 математику до final selection; намеренный AA loss проверяется явно.
- [x] Исправить найденное новое NN-затемнение: прежний working input, final delivery после NN,19 protocol regressions и независимое закрытие2P2.
- [x] Actual native3/writer3 и новые corrected cropNN2/host/writer/dark-white/source/colour/detail loss.
- [x] Полный current pipeline с verified cached actual NN payload при identical input; final2402×4816/48pxpadding/300DPI/hash PASS.
- [x] Profilev15, receiptsv1–v14, components/API1 и inherited UI padding:782 scoped tests+51subtests PASS; независимое review/syntax/sensitive/diff-check PASS.
- [ ] Новый полноразмерный NN execution: timeout600с; cached replay не выдавать за завершившийся новый полный run.
- [ ] Вся остаточная цветная/тёмная линия: уменьшается, но остаётся на actual boards; scope слабого cleanup завершён, исходная visual quality задача открыта.
- [ ] Installed Windows/remote providers: не проверены; сборка/публикация отдельно не разрешены.

Требования/приёмка: STATE.md. История: docs/ERRORS.md#strict-opaque-edge-20261003.

## Повторное исследование automatic каймы по образцу

- [x] Проверить Git/ветку и изолировать исследование от manual RGB tool/precision v13.
- [x] Прочитать прошлые historical/reference проверки и не обнулять negative counterexamples.
- [x] Поручить две независимые сложные части сильным агентам.
- [x] Подтвердить exact reference classifier/solve block:81 executions, admission двух pixels возвращает зелёный край; genuine AA/lines loss доказан.
- [x] Подтвердить float32 endpoint defect позднего повторного despill,30/57 baseline regressions FAIL.
- [x] Внедрить узкий finite/roundoff guard вместе с проверенной weak precision поправкой; profilev14, без AGPL source.
- [x] Проверить combined658 tests+51 subtests,18 known-truth+12 negatives,135 exact exclusions, old receipts/components/UI padding contract.
- [x] Native actual3/source/core/support exact; настоящий final writer3/trim/padding/DPI/hash проверен, existing1 alpha3 trim loss отдельно учтён.
- [ ] Остаточная автоматическая цветная/тёмная полоска: не исправлена на actual3, не выдавать numeric guard за visual fix.
- [ ] Existing hiddenRGB direct API и white-AA material ambiguity: подтверждены отдельно, требуют самостоятельных решений и негативных controls.

Требования/результаты: STATE.md. История: docs/ERRORS.md#automatic-core-reference-cause-20261003.

## Слабый край и порядок операций, 2026-10-03

- [x] Подтвердить ошибку затемнения при делении на floor 0,05 вместо valid coverage.
- [x] Добавить 18 known-truth regressions; baseline 15 FAIL, candidate 255 related PASS.
- [x] Проверить native source/body/тонкие детали и два настоящих local NN фрагмента; final trim/padding/300 DPI PASS.
- [x] Проверить «увеличение до удаления»: отвергнуть цветные полоски/разрывы, не менять порядок автоматически.
- [x] Независимое ревью без новых P1/P2;180+180/30/18/9 controls PASS, root repeat PASS; safe suite2591+284 и49 дополнительных tests PASS.
- [x] Полноразмерный actual local pipeline1254²→2404×4820 с300DPI,source/receipt/RGBA PASS; sensitive scan/diff-check PASS; подготовлено для commit/push без сборки.
- [ ] Остаточная длинная кайма: не считать устранённой по узкому вычислительному исправлению.

Текущий результат в `STATE.md`, история `docs/ERRORS.md#low-coverage-colour-20261003`.

## Прозрачное поле после финального trim, 2026-10-02

- [x] Реализовать одобренный1% от длинной стороны после final trim для automatic.
- [x] Защитить от добавления перед upscale и накопления при repeat.
- [x] Actual supplied PNG,inner RGBA/source exact,transparent border/300DPI PASS.
- [x] State/queue/export/metadata regressions PASS; независимое ревью без новых P1/P2.
- [x] Staged sensitive scan/diff-check PASS; проверенная правка подготовлена для task commit/push. Сборку не запускать.

Требования и результаты: `STATE.md`, история `docs/ERRORS.md#final-trim-padding-20261002`.

## Поздняя цветная кайма, 2026-10-02

- [x] Подтвердить late-boundary shade defect точным эталоном и отдельным provisional input.
- [x] Отбросить whole-RGBA freeze, который ухудшает existing AA/golden mask.
- [x] Source fit + shade agreement: actual guard реализован;229 tests PASS, independent96+96 controls/3negatives и production review PASS.
- [x] Реальные рисунки,2cached NN192→768,final trim/300DPI roundtrip,sourceSHA/body preservation PASS; длинная кайма остаётся.
- [x] Независимое ревью P1/P2 нет; полный safe suite2563 tests +284 subtests PASS,57skip/21deselect.
- [x] Staged sensitive scan/diff-check PASS; проверенная правка подготовлена для task commit/push.
- [ ] Не считать оставшуюся кайму исправленной по одним synthetic tests.

Требования/результаты в `STATE.md`, история в `docs/ERRORS.md#late-boundary-colour-20261002`.

## Автоматический клипарт: trim и300DPI, 2026-10-02

- [x] Переименовать раздел по просьбе владельца.
- [x] Включить alpha trim и300DPI для automatic, включая restore/retry.
- [x] Обрезать прозрачные поля перед post-background upscale, сохранить final trim.
- [x] Защитить белую краску explicit RGBA, pattern canvas, alpha1 и crop URL.
- [x] Проверить supplied PNG реальным final writer и независимым ревью.
- [x] Релевантный safe suite:203 tests +63 subtests PASS; дополнительный11 tests +21 subtests PASS.
- [x] Staged sensitive scan и diff-check PASS.
- [ ] Windows/полный neural сценарий: недоступен до отдельного разрешения на сборку.

Требования и фактические результаты: `STATE.md`, запись
`docs/ERRORS.md#auto-clipart-trim-dpi-20261002`. Сборка и публикация не запускались.


## Повторное перекрашивание уже восстановленного края, 2026-10-02

- [x] Независимо подтвердить shade→false-key projection на точном однотонном фоне, без догадки о неизвестном цвете.
- [x] Зафиксировать regression RED: 12/12 ordinary controls FAIL на 91bec9d.
- [x] Реализовать узкую source-coherence защиту partial RGB только в opaque_clipart, без новых UI/моделей/рефакторинга.
- [x] Проверить staged/automatic, три цвета key, настоящее additive spill: 180 связанных tests PASS, включая 24 новых.
- [x] Actual production native cutout совпал с диагностическим guard; local NN192→768 на цветке/уточке, sourceSHA и PNG roundtrip PASS. Повторное пожелтение слабее, остаточная кайма не решена. Body RGBA глубже3px неизменен, visible→zero нет; последующие refinements меняют некоторые alpha.
- [x] Независимое ревью фактического diff: P1/P2 нет; 9 sparse-mask + 3 large1042×1040 + 3 legacy byte-equivalence controls PASS.
- [x] Первый общий прогон обнаружил один flaky concurrency subtest; зафиксирован controlled RED/GREEN, исправлена только синхронизация теста/helper, без ослабления equality. docs/ERRORS.md#parallel-capacity-timing-20261002.
- [x] Финальный safe pytest: 2520 tests + 281 subtests PASS за438,65с, 57 skipped/21 network-paid deselected; independent source/test review и staged sensitive scan/diff-check PASS. Проверенный набор подготовлен в текущей task branch для передачи через Git.
- [ ] Остаточная кайма, точность первого матта и полный5016/Windows: отдельные незавершённые проверки; docs/ERRORS.md#repeated-staged-despill-20261002.
- [ ] Сборку и публикацию не выполнять без отдельного поручения.

## Чёткость с предпросмотром и остаточный цвет, 2026-10-02

- [x] Одобрен новый макет «Сделать край чётче»: один шаг, До/После, Отмена/Применить, без силы.
- [x] Реализовать только явную alpha-правку, без RGB, новой модели и изменения автоматического конвейера.
- [x] Проверить cancel/stale/save/file-switch/keyboard/Undo/Redo, повторный отдельный шаг, лимит и отказ без утраты Undo:57target tests PASS.
- [x] Actual Qt/5016² владельца: preview без изменения mask/history, Apply из До, Undo/Redo, copy PNG/sourceSHA exact;0,753с preview,3,751с save на Linux.
- [x] Сравнить approved/actual1120×780, включая пустой редактор, предел и доступ к кнопкам прокруткой; docs/ui/3.2/edge-sharp-preview/.
- [x] Независимое source-review и9 дополнительных Qt проверок PASS; P1/P2 не обнаружены.
- [x] Общий безопасный pytest: 2494 tests + 281 subtests PASS, 57 skipped/21 network-paid deselected; ещё 2 регрессии из независимого ревью PASS после полного прогона, production source не менялся.
- [x] Staged sensitive scan и diff-check PASS; итоговый файл инструмента с обеими новыми регрессиями: 14 tests PASS. Проверенный набор подготовлен в текущей task branch для передачи через Git.
- [x] Проверить оттенки отдельно: локальный B, foreground ML/CF/U2 prior, сохранение площади, настоящее NN после коррекции и локальная ретушь. Не внедрять отвергнутые прототипы.
- [ ] Остаточная цветная кайма: качественное универсальное автоматическое исправление не найдено; продолжить отдельно от alpha. Причины/попытки в docs/ERRORS.md#edge-colour-background-ambiguity-20261002.
- [ ] Возможный один ползунок в preview: владелец спросил о нём; новый макет/поведение пока не согласованы. Дополнительные кнопки сейчас не добавлять.
- [ ] Сборка только по отдельному поручению; Windows, полный neural5016 и установленные модули не проверены этим этапом.

## Сужение ×2: проверка защит и цвета, 2026-10-02

- [x] Учесть предпочтение владельца: обычное ×2 лучше защищённого варианта со второй полоской.
- [x] Проверить две защиты; после потери линии отменить подготовленное подключение и установить причину на точном контрпримере. Не угадывать новые детекторы ширины.
- [x] Независимые 420 штрихов и 3360 повёрнутых сцен; главный агент повторил потерю 60 непрозрачных пикселей. Это обнаруженная ошибка, не готовое исправление.
- [x] Реальные локальные нейропрогоны: Animevideo4, Photo4 до удаления фона, два фоновых композита уточки/цветка и непрозрачного эталона. Без загрузок моделей.
- [x] Проверить двойной маттинг и RGB-коррекцию: свободный вариант ослабляет тело/линию, ограниченный недостаточно устраняет полосы. Не переносить прототипы в production.
- [x] Сохранить восемь стадий удаления фона, проверки и диагностические сценарии вне Git; обновить STATE и docs/ERRORS.
- [ ] Подтвердить улучшение одновременно по чёткости, цвету и сохранению деталей. Текущие варианты не выполняют все требования. Далее исследовать восстановление цвета исходного края: тёмные оттенки присутствуют уже в staged_result.
- [ ] После подтверждения алгоритма реализовать узкое исправление, добавить регрессии и провести независимое повторное ревью; сборку не запускать.

## Следующий этап: чёткий край для разных стилей, 2026-10-02

- [x] Учесть уточнение владельца: непрозрачный объект, прозрачный фон, чёткий край с минимальным сглаживанием; модель «Фото» не универсальный ответ.
- [x] Проверить существующие контракты сплошного объекта, цвета края и тонких деталей: 42 теста и 20 дополнительных проверок прошли.
- [x] Сравнить переход прозрачности на трёх эталонных формах и двух пользовательских фрагментах; независимая проверка 420 штрихов выполнена.
- [x] Проверить варианты без перекрашивания и показать сравнения. Жёсткий порог и сильное сужение удаляют реальные кончики; щадящий вариант улучшает край умеренно.
- [ ] Подтвердить восстановление непрозрачности тонких нарисованных деталей: щадящий прототип пока сохраняет их видимость, но не решает это требование.
- [ ] Установить безопасное исправление остаточного RGB края отдельно от маски.
- [ ] Менять алгоритм только после воспроизводимого улучшения; добавить регрессионную защиту и независимое ревью. Новые пользовательские настройки пока не добавлять.

## Новый этап: сравнить порядок обработки

- [x] Проверить доступные runtime/model без загрузок, dependencies и платных вызовов.
- [x] Existing Linux NCNN + cached software Vulkan,32px actual probe PASS.
- [x] Actual identical Clipart×4/2orders×2crops,Photo×4/2crops,Clipart×2/duck:7neural outputs. PNG/sourceSHA/alpha PASS.
- [x] Actual13flower petals/leaves иroughduck feather crop; dark/white backgrounds, independent visual/pixel review PASS; только crop conclusions.
- [x] Варианты готовы: natural watercolor remove→Photo×4; crisp lines remove→Clipart×4; upscale→remove не universal. Сохранено в researchbranch; production defaults не менялись.
- [ ] Полноразмерный/native Windows сценарий только с доступным runtime и разумным локальным бюджетом; сборку/публикацию не запускать.

## Текущая реализация: контур, край и восстановимый экспорт

- [x] Отдельная fixbranch;5016px baseline отказ исправлен без уменьшения PNG.
- [x] Bounded proposals/ownership/UndoRedo/save/RGB:188target и независимые61+48cases PASS; финальный actual5016² PASS.
- [x] Per-call weak-paint/profilev11 guard:196focused/52+12contracts и independent230+6PASS; paired performance/memory budgets соблюдены.
- [x] Owner промежуточные PNG сопоставлены; bilinear alpha и alpha0 RGB input исправлены; independent6+3tests/70controls PASS.
- [x]20→1, active/inactive/history/paid evidence и explicit canceled continuation:123+9tests, independent28targeted PASS.
- [x] Table export approved и реализован: English defaults/save/partial;Финальные46+5UI/planner/integration PASS; independent52+10 и50toggle/reopen cycles PASS; actual save/freeze PASS.
- [x] Actual ready/issues/empty/partial1120×780, footer reachable; approval artifacts в docs/ui/3.1/export-table-20261002/.
- [x] Общий safe suite2481passed+281subtests;1exact dependency inventory failure исправлен после независимого review,26targeted checks PASS. Production source не менялся после full run; artifact/AST/diff guard PASS.
- [x] Подготовить проверенный source handoff в codex/fix-large-contours-edge-quality-20261002; точный commit и upstream-status указаны в Git этой ветки. Сборку/production не запускать.
- [ ] После отдельно разрешённой сборки: native Windows upscaler RGB quality и installed licensed delivery; старые beta сохраняются до приёмки.

## Новый сценарий: уточка5016×5016

- [x] Проверить реальный PNG и воспроизвести отказ actual contour worker.
- [x] Устранить ограничение редактирования5016px с сохранением размера/деталей, добавить meaningful regression; docs/ERRORS.md#party-duck-5016-contour-quality.
- [x] Промежуточные PNG локализовали alpha ringing, временный RGB input исправлен; mask-only проверка не доказывает исправление уже встроенных neural RGB полос. Native повторный запуск после сборки.

## Диагностика края после обсуждения, 2026-10-01 (дата владельца)

- [x] Разделить цвет и alpha в новых сравнительных PNG на текущем a3f0b70.
- [x] Проверить реальные13/07/14/14_ready, actual белые мишку/хвою,2knowntruth masks и detached-detail control; источники сохранены.
- [x] Количественно подтвердить потерю деталей при opening3×3, оформить ограничения и сравнения; STATE.md и docs/ERRORS.md#edge-separate-comparison-20261002.
- [ ] Обсудить результат с владельцем. Общая очистка/новые ползунки не согласованы; код Studio не менять по результату одного визуального сравнения.

## До следующей сборки, поручение2026-10-01

- [x] Создать отдельную ветку кандидата, сохранить исходные worktrees.
- [x] Совместить contour/direct-entry/zoom/module-outline/upcoming desktop;90target tests PASS.
- [x] Закрыть воспроизведённое перекрашивание pale края:187tests PASS,actual13/07 source preservation и PNG roundtrip PASS; ограничения ambiguity сохранены.
- [x] Завершить белый режим: visual approval получен, UI/worker/settings/restoration подключены.107target+6subtests и79UI/flow+5subtests PASS; actual production worker на2real PNG PASS для RGB/alpha/source/PNG. Качество всех деталей/Windows не подтверждено.
- Отложено с согласия владельца: раздельные RGB/alpha регуляторы обсуждать после проверки качества. В текущий кандидат ползунки не добавлять.
- [x] Final safe regression after white integration:2419tests+278subtests PASS392.23s,57skip/21deselected; final independent46tests+9subtests PASS7.56s. Два inventory failures исправлены точечно.
- [x] Проверить source/package contracts:41tests+9subtests PASS. Локальный HTTPS admin→candidateQt1PASS. При будущей сборке переиздать processing/image-processing, назначив совместимость с новым Core.
- [x] Проверенный исходный кандидат сохранён в отдельной ветке codex/prepare-studio-next-20261001; development/release unchanged. Интеграция eeec47f и завершение белого режима переданы через origin; точный финальный source commit указан в Git этой ветки.
- [ ] Сборка только по отдельному поручению. Windows delivery/upgrade после сборки, старые beta не снимать до приёмки.

## Остаточная светлая кайма, 2026-10-01

- [x] Воспроизвести пожелтение тонкой детали на baseline13d30af.
- [x] Локализовать два этапа и проверить offline прототип:148tests и27known-truth cases PASS.
- [x] Подготовить experimental13/07; проверить SHA и PNG roundtrip.
- [x] Провести независимое read-only ревью: кандидат требует дополнительных проверок.
- [x] Проверить highlight+additive и значения около1.01:18cases, риск прототипа подтверждён.
- [x] Компромисс сохранения исходной светлой краски при ambiguity ранее согласован; опасный scale prototype отклонён, выбран узкий production guard. См. top candidate и docs/ERRORS.md#pale-material-policy-fix-20261001.
- [x] Guard в обоих этапах интегрирован и проверен187tests; не обещает снять любую additive засветку.
- [ ] Отдельно обсудить RGB/alpha регуляторы; не переносить небезопасные reference defaults.

Текущий статус: STATE.md; история docs/ERRORS.md#pale-rim-followup-20261001.

## Следующие решения по интерфейсу и прозрачности

- [x] Одобрены и реализованы одна кнопка без стрелки, бирюзовый контур действия и centered responsive grid349×248.8targetQt и105broader tests+10subtests PASS.
- [x] Offline сравнение параметров прозрачности:143выполнения,7synthetic/1bear-proxy/3real images, sourceSHAunchanged. Main подтвердил количественный loss на цветах; реальные perfectmasks неизвестны.
- [ ] Обсудить раздельные регуляторы цвета/alpha. minIsland не переносить как универсальное сглаживание; алгоритмы/ползунки пока не менять.
- [ ] Windows-проверка прямого входа после отдельно разрешённой сборки.


## Цвет края и прямой вход в прозрачность, 2026-10-01

- [x] Воспроизвести жёлтый край лепестка на13.png, выделить staged chroma prior как причину.
- [x] Добавить локальный prior и57регрессий (petal/RGB keys, mixed rim width/shading/hue).
- [x] Общие проверки:347distinct tests+46subtests PASS; independent157tests+60baseline comparisons PASS. Обычные смеси сохранены, неоднозначная additive-примесь может остаться.
- [x] Финальные transparent13/07 PNG и comparison подготовлены; actual save/reopen/frame/source preservation PASS. Все ореолы иWindows не подтверждены.
- [x] Показать прямой вход рядом с выбором файлов; владелец отклонил расположение.
- [x] Показать исправленный left-menu mockup: empty/selected/editor.
- [x] Visual approval получен; прямой вход, возврат к файлам и отдельная копия реализованы.139tests+31subtests и122tests+9subtests PASS; actual1120×780 screenshots сохранены.
- [x] Прямой вход включён в chain кандидата eeec47f и отправлен; сборку/публикацию не выполнять.

## Ctrl + колесико, 2026-09-30

- [x] Масштабирование в inline transparency editor вверх/вниз с Ctrl; обычная прокрутка сохранена.
- [x] Actual Qt viewport events:42tests PASS, включая brush/pen, fit/limits, fractional/pixel delta и mask preservation.
- [x] Включён в candidate chain ce09cb4→eeec47f; Windows-сборка пока отложена.


## Пиксели после правки Безье, 2026-09-30

- [x] Воспроизвести остатки старого края; устранить причину локально с сохранением отдельных деталей.
- [x] Real Qt apply/save/reopen/RGB/Undo/Redo; root115tests и independent review PASS.
- [x] Крупное synthetic4100px изображение: apply0.252s, UI gap87.8ms.
- [ ] Проверить исходный PNG владельца до и после правки, когда файлы доступны.
- [x] Интегрировано в candidate chain eeec47f; Windows-сборка отложена.


## Названия рецептов обработки, 2026-09-30

- [x] Короткие названия, без пояснений; состав операций сохранён.
- [x] Actual Qt выбор рецептов/свои настройки и screenshot PASS; 44 tests + 5 subtests PASS.
- [x] Интегрировано в candidate chain eeec47f; сборка отложена владельцем.



## Продолжение: кандидат Studio3.2.11 / modules1.5.2

- [x] Подтвердить residual paidhistory eviction и закрыть implicit paid resubmit; provider-success checkpoint, repeated retry/reopen regressions, independent review PASS.
- [x] Согласовать source version/Azure default3.2.11; подготовить6official signed1.5.2 modules minimumCore3.2.11, package/runtime/Qt checks PASS.
- [x] Final full source2145tests+278subtests PASS, sensitive tracked scan и независимое ревью PASS.
- [x] Source commit9400729 создан в отдельной ветке.
- [x] Push9400729 после отдельного явного разрешения владельца; origin feature branch, без merge.
- [x] PUBLIC → Windows production build exact9400729 → PRIVATE: run36783850992 SUCCESS; root и независимый агент подтвердили PRIVATE.
- [x] Installer3.2.11/source/hash/provenance совпали; installed frozen Core13checks PASS, каталог просмотрен.
- [ ] Actual licensed module download/open in installed Windows; источник и package smoke не заменяют этот сценарий.
- [ ] Проверить обновление старой установленной3.1.4 с сохранением пользовательских данных; legacy fixture шаг CI SKIPPED.
- Новые серверные релизы не публиковать без отдельного поручения.

## Исправления полного ревью, 2026-09-30

- [x] R1/P1: явный отказ лицензии прекращает автономный доступ.
- [x] R2/P1: повтор части очереди продолжает принятую provider-задачу.
- [x] R3/P1: оплаченный raw остаётся доступен после ошибки обработки.
- [x] R4/P1: ошибка сохранения не приводит к потере проекта при выходе.
- [x] R5/P2: самостоятельный рецепт300DPI публикует PNG.
- [x] R6/P2: миграция сохраняет выбранную модель и runtime.
- [x] R7/P2: редактор обновляет QC/доступность экспорта.
- [x] R8/P2: историческая версия не блокирует совместимое обновление.
- [x] R9/P2: clock-skew policy едина для подписи и доступа.
- [x] R10/P2: непрозрачный мех на красном фоне сохраняет RGB/alpha.
- [x] R11/P2: Composer выдаёт новые варианты после сохранения/смены locks.
- [x] R12/P3: одноимённые профили выбираются отдельно.
- [x] R13/P3: редактор сохраняет lineage для безопасной cleanup.
- [x] Локальная HTTPS-доставка:18 tests PASS с тестовыми лицензиями/ключами.
- [x] Независимое повторное ревью финального diff: подтверждённых замечаний не осталось.
- [x] Итоговый полный безопасный прогон:2132 tests+278subtests PASS,57skip/20deselected; сборка не выполнялась.
- Сборка, новые ZIP/релизы и публикация не разрешены этим поручением.

- [x] Integrate processing fix with delivered Studio3.2.9 in isolated3.2.10 branch; preserve both histories and push548b2a6.
- [x] Prepare all six official signed module1.5.1 candidates; verify each signature/install/runtime and >=3.2.10 compatibility.
- [x] Complete Windows3.2.10 build and restore PRIVATE: run36723401830 SUCCESS, independent GitHub API verification PRIVATE; version/source/SHA256 verified.
- [x] Installed Windows Core acceptance: all13 checks PASS. Prepare seven-entry beta kit: Studio3.2.10 + all six module1.5.1 ZIPs, hashes and runtime/UI receipts.
- [x] Owner requested publication: Studio3.2.10 and six module1.5.1 rows published directly in beta; all7 beta discovery PASS, stable discovery absent; stored hashes/sizes verified, old releases unchanged, backup verified, health200/download-token403.
- [ ] Actual licensed module download/open in installed Windows; installed Core and Linux package UI checks passed, real customer delivery scenario not yet tested.

## Studio shell and separately installed modules

- [x] Owner correction: move Studio3.2.9 and all six module1.5.0 packages to beta.
  Verified all seven absent in stable and present in beta; no other release changes.

- [x] Base 6568fae / Windows 3.2.8 verified from existing handoff; new isolated branch.
- [x] Read-only production server audit: healthy beta-modules-53b42ef; Club/VIP
  grants four existing workflows; published Windows module packages 1.4.x exist.
- [x] Catalog mockup reviewed; apply owner refinements (no status/refresh strip,
  updates in header, existing artwork dimensions, new composer slot-machine art).
- [x] Unified catalog actions and first-install flow; installed packages required.
- [x] Decouple shell startup/project metadata from bundled workflow discovery.
- [x] Port Composer without reverting 3.2.8 text models or shared-service changes.
- [x] Package Composer as signed independently loaded code; no bundled fallback.
- [x] Frozen shell excludes module-owned implementations; Core startup and local
  engines verified in Windows run36663221787. Actual module opening below remains separate.
- [x] Source integration tests: denied/unknown/offline, download/cancel/error, reopen,
  independent update, invalid signature and revoked rights;18 HTTPS tests passed.
- [x] Independent review findings: serialize license activation/check persistence;
  clear rejected access and discard stale account results; regression tests.
- [x] Independent review and fixes, full source suite2046tests+273subtests,
  Qt1120×780 comparison; limitations documented.
- [ ] Installed native Windows module download/open acceptance; source HTTPS passed.
- [x] Prepare signed Windows module1.5.0 candidate ZIPs (Studio>=3.2.9,<3.3.0),
  inspect signatures/compatibility; uploaded as draft after owner authorization.
- [x] Commit/push implementation512e6a1 and draftPR#2 on top of3.2.8 source;
  no merge. Full local suite passed; temporary public CI now owner-authorized.
- [x] Windows shell build and installed smoke: run36663221787 SUCCESS,
  source1a2f311. No billing change.
  Owner subsequently authorized release artifact publication; license grants
  and deployment/code changes remain outside scope.

Server audit: Composer has no customer assignments; its release draft is uploaded.
Customer grants remain unchanged. Owner authorized publishing release rows.
- [x] Upload six module1.5.0 drafts, verify hashes and create private DB backup.
- [x] Complete corrected run36663221787, restore and confirm PRIVATE GitHub visibility.
- [x] Verify installer, upload Studio3.2.9 and publish all seven release rows.
  Hashes match, release discovery confirmed; /health200, unauthorized download403.

## Processing method choices
- [x] Restore existing background provider/model and chroma-colour controls in Processing per owner request.
- [x] Add per-file Auto RGB chroma detection with metadata priority and uncertainty refusal; compact Processing dropdowns.
- [x] Fix seven settings tests by isolating protected-credential user paths; full suite has zero failures.
- [x] Independent review: fix Auto startup migration and stale model tooltips; verify both corrections.
- [x] Prepare integration with delivered 3.2.9: automatic code merge, preserve both histories in three documentation conflicts.
- [ ] Native Windows and installed-build acceptance of restored Processing choices.
- [x] Separate white-background method implemented after owner mockup approval, independent cached U2Net segmentation; not part of RGB chroma contract. Source/worker/UI checked, full quality and Windows acceptance pending.

- [x] Clarify new chroma prompts: preserve object textures, exclude paper substrate
  and white bridges/fringe; foliage gaps use the selected background colour.
- [ ] Verify one regenerated teddy/pine image after updating prompts; paid launch
  requires agreed provider/model/cost. This refinement is not in installer3.2.7.

- [x] Address independent P1 review: block close/project switch during embedded
  ZIP export; recover saved generated PNGs without repeating generation, retain
  source paths and completed-stage provenance across retries and reopening.

- [x] Fix independent review findings: incomplete background removal/upscale
  must not become ready on PNG save; preserve correction access and failed
  status across reopening. Include provider/model/request count in paid quote.

- [x] Per final owner decision, retain compact prompts without colour badges;
  verify hidden background/reference instructions survive edits without duplication.

## Text model picker and requested follow-ups, 2026-09-29

- [x] Add Ideas/Model text tabs with provider/model dropdowns and additional models.
- [x] Preserve saved automatic-mode selection; no generation on model selection.
- [x] Explicit per-run active-reference image consent and capability checks.
- [x] Connect KIE Claude text requests, native response parsing and dated estimate.
- [x] Confirm Gemini KIE numeric pricing and documented OpenAI-compatible route.
- [ ] Replace dated KIE estimates with maintained tariff retrieval before
  expiry on 2026-10-29; never silently extend unverified prices.
- [x] Windows3.2.7 build36612613865 and native installed smoke passed; installer
  checksum/source verified. CI36612608520 passed. No update publication.
- [ ] Owner manual real-image acceptance and separately authorized live API checks.
- [x] Owner chose to remove the texture control entirely; ignore legacy material
  values in new editor snapshots and prompts, preserving style and object details.
- [x] Owner approved manual pen with double-click closure; implement and verify
  remove/keep inside, point/mask undo, redo and keyboard zoom (74 tests passed).
- [x] Processing-module batch local cutout via U2Net, shared hard-mask helper,
  source preservation, failure/cancel guards and saved editor-copy handoff.
- [x] Direct shortcut from generated results to Processing: selected saved PNG,
  preserve original project, no automatic processing or overwrite.
- [x] Remove direct automatic-flow dependency on export UI: create embedded and
  modal views through RunResultsExtension; architecture baseline passes unchanged.
- [x] Run integrated isolated offline suite; align legacy texture acceptance
  with owner decision and verify persistence without reintroducing the field.

Evidence: docs/ui/3.2/text-model-picker/README.md. No build or paid call performed.

## Inline transparency tools, 2026-09-23

- [x] Inspect modal contour flow and prepare full-context brush/Bezier mockups.
- [x] Obtain visual approval, including subsequent icon/preset/keyboard refinements.
- [x] Integrate Bezier with existing editor, shared applied-mask undo/save and preserved zoom.
- [x] Verify combined brush/Bezier edits, saved alpha/RGB and actual UI.
- [x] Complete full offline checks and targeted final regression checks.
- [x] Support4100px per side; background extraction/application and cancellation.
- [x] Prove local ROI/full raster equivalence and benchmark2048/4096/4100 with UI heartbeat/RSS.
- [x] Build ordinary Windows3.2.6 (35927420792); verify SHA/provenance, installed editor
  and original3.1.4 upgrade. Final-source CI35927397240 passed.
- Publication of3.2.6 has not occurred.


## Complete Images3.1.4 migration, 2026-09-23

- [x] Unify server module catalogs and deploy missing Automatic Clipart option.
- [x] Apply owner-approved Club/VIP all-workflows rule, preserve individual rights.
- [x] Write exact Russian release/module/bundle/news checklist in service repo.
- [x] Separate Studio display branding from legacy persistent storage identity.
- [x] Add real Bezier edit/save/undo/redo verification to installed-app smoke.
- [x] Verify Windows3.2.5 installation over original published3.1.4 and publish
  hash-verified ordinary installer. Fix server compatibility for old updater.
- [ ] Arrange and verify off-host publisher-key backup with owner.
- [x] Prepare verified production packages and upload five unpublished admin drafts.
- [ ] Publish five prepared module drafts after owner confirms off-host key backup.


## Independent Components and Home News, 2026-09-23

- [x] Implement approved shared processing boundary: signed package, stable API,
  engine injection, real profile receipts, consumer-derived rights, job leases,
  atomic activation/rollback. Retain existing workflow Update buttons, no extra row.
- [x] Move actual planning/prompt dependency chain into workflow inventories and
  verify installed packages use their own rules without mutating signed files.
- [x] Verify real HTTPS delivery, tamper/compatibility rejection, active-job pinning,
  rollback and the three processing consumers. Backend PostgreSQL suite: 210 pass;
  HTTPS integration: 17 pass. Final offline suite result is recorded in STATE.md.
- [x] Obtain approval for independent news home/admin mockups and implement draft,
  publish, withdraw, protected signed feed, latest-news rendering and offline cache.
  Preserve approved/actual evidence in `docs/ui/3.1/independent-components-news/`.
- [x] Verify browser editor scenarios and offscreen home populated/empty/offline
  states; document the backend migration and ordered rollout requirements.
- [ ] Decide ordinary Generation chroma/online-removal behaviour with the owner;
  existing capabilities remain available until that product decision.
- [x] Owner authorized commit/push, backend deployment and Studio build. Working
  and test services upgraded with backups and verified health/data preservation.
  Test3.2.4 build and native installed checks passed; compatible test modules published.
- [x] Ordinary Studio3.2.4 artifact verified (run35890152199): Windows checks,
  installer hash/version/provenance. Final Linux CI35891569726 passes.
- [ ] Owner manual installed UI/image acceptance. Ordinary3.2.5 is now published;
  production module drafts await off-host key backup. No announcements published.


## Edge Color Artifacts Reported by Owner, 2026-09-22

- [x] Owner visually accepted the v9 two-duckling PNG and explicitly authorized
  commit/push on 2026-09-23. Acceptance is limited to this sample; broader quality
  and the known memory/red-key issues remain open.
- [x] Establish delivery scope: v9 Local Chroma Key is shared by Automatic
  Clipart, Generation and Processing; new planning/compiled-prompt guidance is
  used by Automatic Clipart. Pinterest and existing saved prompts are unchanged.
  Both implementations are Core shell dependencies, absent from workflow ZIP
  inventories; delivery requires an explicitly authorized Studio build/update.

- [ ] Implement owner's selected Clipbrook-equivalent quality target. Exact
  default reference and three ablations are in owner-clipbrook-comparison-20260922.
  Owner confirmed Vibix must remain closed. No AGPL source integration or
  relicensing is authorized; implement mathematical operations independently.
  Current edge-mixture and key-spill changes remain under visual review; residual
  colour and the newly reported bright fringe block overall acceptance.

- [x] Diagnose and reduce remaining blue specks and pink/red edge contamination
  on the v8 owner image. Add local chroma repair and recovery of wrongly opaque
  mixtures; preserve existing partial/zero alpha and genuine material hues.
  Receipts v9; 24 new regression cases. Current artifacts and single white
  before/after sheet: `artifacts/owner-edge-spots-20260922/` beside the worktree.
- [x] Verify final v9: 1885 passed, 57 skipped, 18 deselected, one existing
  expected red-fur failure. Syntax, tracked-artifact guard, isolated offscreen
  startup and diff checks pass. Review PNG hashes match the tested sources.
- [x] Obtain owner visual acceptance of v9 for the supplied two-duckling image.
  Four weak diagnostic key-coloured samples
  and some fine edge residue remain; do not claim a fully clean edge.
  Six fur/four botanical mean errors improve or hold on white/black;
  no newly altered true opaque pixels. Check the saved PNG, not test count alone.

- [x] Fix out-of-gamut mixture recovery turning feather edges white/yellow.
  Handle additive key spill without globally capping real highlights. Fifteen
  regressions added; 66 targeted checks pass. Receipts advance to v8. Review
  sibling `artifacts/owner-edge-brightness-20260922/`; Before is the previous v7
  result. Source/previous/corrected crops include the central and right edges.
- [x] Verify v8: full isolated run 1861 passed, 57 skipped, 18 deselected,
  one existing red-fur expected failure. Syntax, sensitive tracked-artifact
  guard, isolated offscreen startup and diff whitespace checks pass.
- [ ] Review the brightness correction visually. Known-truth textured-fur white
  error slightly worsens (blue 18.927 -> 19.408; green 6.476 -> 6.693), with small
  black-background improvements; opaque texture and botanical checks hold.
  Do not claim universal improvement or full Clipbrook parity from this fix.

- [x] Separate foreground brightness from coverage in the opaque staged path;
  reconsider contaminated rim pixels before solving and preserve material-local
  references for thin stems. Add source-consistency and painted-detail guards.
  Six direct regressions on three keys reproduce the old alpha255 defect and
  recover RGB with alpha200 versus truth204. Final edge file: 35 cases pass.
- [x] Earlier v7 full isolated verification: 1846 passed, 57 skipped, 18 deselected,
  one existing expected red-fur failure; syntax, tracked-artifact guard,
  isolated offscreen startup smoke and diff whitespace checks passed.
- [x] Obtain owner visual acceptance of
  `artifacts/owner-edge-spots-20260922/ducklings-transparent.png`; the compact
  comparison shows the preceding v8 result and the current correction.

- [ ] Broader quality validation after the earlier rejected candidates and the
  now-approved v9 duckling sample. Acceptance on further inputs requires clean
  white/black composites, intact feather detail, original subject colours and
  preserved small gaps, not merely fewer blue pixels or passing unit tests.
- [x] Compare joint alpha/foreground reconstruction and existing BEN2 on the
  owner's actual source. Both rejected: the former damages genuine texture in
  six-case known-truth testing; BEN2 leaves halos and softens feathers. Keep
  both as diagnostic artifacts only; neither is integrated as a replacement.

- [x] Retain supported staged key-mixture solutions before opaque source-RGB
  restoration. On the real ducklings input, high-blue fragments fall 200 -> 30;
  deep opaque RGBA and existing transparent areas are unchanged. Ten regression
  cases protect source mixtures, painted blue marks and disconnected details.
  Affected suite: 247 passed, 1 environment skip, 1 existing expected failure.
- [ ] Finish remaining key-coloured and fine coloured edge fragments on the owner's actual two-duckling
  raw image (`artifacts/owner-ducklings-source-20260922` beside the worktree).
  Latest result leaves 30 visible blue-dominant pixels (alpha >=128,
  B-max(R,G)>35), versus 200 at initial diagnosis. The legacy profile leaves
  zero but is not a safe wholesale replacement for opaque fur. At least 125
  partial pixels are promoted to opaque by texture recovery, including measured
  key mixtures; some blue fragments are classified opaque even before recovery.
  Preserve genuine pale fibres and the small transparent gap between heads.
- [ ] Address real staged-input peak memory at 2048px: 488.25 MiB with this fix,
  487.398 MiB with its guard disabled; canonical fixture performance alone does
  not establish the same memory bound on detailed real inputs.
- [ ] Obtain the matching final transparent PNG and any saved processing/upscale
  stages for the same `13.png`; current output is a new local source-code run,
  not the owner's installed-app result.
- [x] Stop staged edge correction from recolouring established opaque
  botanical pixels in the opaque-clipart profile. Off-blue known-truth cases
  at 256/512px now have zero changed opaque RGB pixels (previously 218/987).
  The strict botanical checks pass; 120 related tests pass, one existing red-fur
  expected failure remains. No real owner PNG validation or release yet.
- [ ] Resolve the partial-edge tradeoff after opaque botanical RGB preservation:
  off-blue white composite mean improves, but black mean worsens at both sizes.
  Inspect actual raw and final PNGs before calling the cutout acceptable.
- [x] Record owner's old flower screenshot and handoff in STATE.md (2026-09-22).
  Screenshot is fully opaque with baked black background, not original alpha.
- [ ] Investigate reported muddy small flowers, coloured leaf/stem fringes and
  interior bands using raw/final PNGs and stage snapshots. Stage responsible is
  unknown; separate generation, removal, colour correction and upscale. Protect
  opaque interior colour/texture; no broad-band recolouring or global blur/erosion.
- [x] Add botanical fixtures at two sizes and blue/off-blue backgrounds. Fix
  staged final smoothing turning established opaque petals/stems translucent;
  672/2150 alpha deviations become zero, with genuine gaps preserved.
- [x] Remove staged botanical opaque colour drift up to 13/255. Exact RGB,
  opacity and holes now pass at both tested sizes and both blue keys; partial
  edge quality remains a separate open item above.
- [x] Add small-detail quality guidance to automatic planning and compiled RU/EN
  prompts: readable petals/leaves, continuous stems, no miniature contact sheet,
  no defocus/fused parts; preserve explicit counts and opaque painted styles.
- [ ] Validate real generated small flowers/branches separately from background
  removal and upscale. Actual owner model/resolution/raw PNG are unknown. Code
  defaults to 1K, but this does not establish the owner's chosen settings. No
  provider model/resolution/cost changes or paid quality trials authorized here.
- [x] Extend partial-boundary recovery only within 12px and with same-component
  references agreeing at two erosion depths, tight fit and in-gamut RGB. Tests
  reject disconnected subjects and conflicting shallow/deep colours. Seven-case
  white/black mean errors improve, opaque damage counts unchanged; not perfection.
- [x] Compare unchanged pinned Clipbrook Core against current Vibix on seven
  identical fur inputs, with known truth and white/black composites. Record
  provenance and raw PNGs in artifacts/clipbrook-vs-vibix-20260922 beside worktree.
- [x] Fix early unguarded enclosure promotion of subpixel gaps in opaque profile.
  Two regressions cover flat/textured blue fur; six golden outputs unchanged.
- [ ] Resolve remaining dominance-based boundary coverage bias using trustworthy
  foreground references. A wider radius alone is not a verified solution. The
  subpixel-gap fix is limited: textured-blue white mean error 29.743 -> 29.406,
  black 17.008 -> 16.626; the visible blue fringe is NOT fully fixed.
- [x] Test flat/textured furry known-truth objects on three key colours, capture
  stages and white/black composites. Offline evidence: `artifacts/chroma-fur-20260922`.
- [x] Recover opaque interiors without flattening the whole alpha mask; exact
  RGB/full opacity checks cover six furry scenes and nine yellow/blue variants.
  Protect real holes and source alpha. Both precise/staged paths covered.
- [x] Independent Astra review; protect fractional openings from overfill.
  Connected fixed-chroma continuation preserves shade without hue drift and
  passes flat red fur; seeds/candidates explained by key mixture are excluded.
- [ ] Finish outermost warm fur pixels on red key and blue-boundary quality.
  Red damaged pixels fell 7162 -> 201 -> 70, remaining within 2px; blue RGB outliers
  fell 187 -> 61 -> 9, remaining within 1px. One strict expected-failure test in
  `tests/test_chroma_fur_probe.py` remains open. New fibre AA metrics also need
  improvement; the source change is not yet an edge-quality release candidate.
  Do not confuse this with the separately fixed v6 colour-projection defect.
  No fixed five-pixel boundary applies to the owner's reported issue.

- [x] Reproduce one colour-compensation failure independently: yellow opaque
  edge details become green during precise opaque-spill projection. Reject
  unsupported/out-of-gamut colour unmixing without changing alpha or blurring.
  Twelve regression cases pass; all six existing goldens retain their metrics.
  Evidence: `artifacts/chroma-color-correction-20260922` beside the worktree.
- [ ] Include the verified source correction (profile v6) in a separately
  authorized future Studio build. The delivered 3.2.3 installer is unchanged.

- [ ] Investigate reported black/dark-blue bands a few pixels from the object
  boundary and isolated red/blue/green pixels along an otherwise yellow edge.
  Owner reports these colors were absent from the generated source. New Windows
  images did not arrive in this task; exact build, processing settings and affected
  stage are not verified. Do not label this a confirmed despill or upscale cause.
- [ ] When files are available, compare the original, background-removal output,
  color-cleanup output and upscaled final PNG at identical edge locations. Inspect
  RGB and alpha separately and composite on white/black backgrounds. Preserve
  working files and identify the first stage introducing the artifact before
  changing the algorithm; do not hide it by globally blurring or eroding edges.
- [ ] Add a regression from the reproducible case: no introduced colored speckles
  or dark bands, with genuine yellow detail and the object contour preserved.
  Edge-quality acceptance remains open independently of passing automated tests.

## Acceptance Correction Delivery, 2026-09-21

- [x] Implement first source pass for the owner's acceptance corrections below.
- [x] Astra review of production changes; preserve legacy custom dropdown values.
- [x] Resolve reference upgrade/retry/lifecycle findings with regression tests.
- [x] Complete full offline tests (1748 passed), signed package and native Windows
  build (35666003342, Studio Test 3.2.3, installed startup/local processing passed).
- [x] Deliver Studio Test 3.2.3 plus auto-clipart 1.3.0 to isolated acceptance;
  signed HTTPS update/downloaded controller/home resume verified, installer
  checksum/provenance verified, owner ZIP prepared with README and no secrets.
- [ ] Owner verifies installed UI and real generation/edges. The detailed items
  below stay open until their full stated acceptance evidence exists; source
  implementation alone does not mark native or paid acceptance complete.

## Automatic Clipart, 2026-09-19

Acceptance requirements dated 2026-09-21 below supersede older checkpoint
directions for planner-image upload, mandatory object forms and six-style `All`
views. Historical completion marks describe earlier increments, not acceptance
of this new workflow. Scope is `auto-clipart` and Studio home; legacy `clipart`
rights/projects and other modules do not acquire the new behavior implicitly.

- [x] Diagnose deferred Pinterest worker-routing test timeout: opaque fixture
  invoked real rembg imports. Use a pre-cut PNG, assert remover is never called
  and the real worker returns a successful variant; keep the original timeout.
- [x] Prepare test-signed auto-clipart 1.2.0 requiring Studio >=3.2.2; verify
  actual 1.1.0 -> 1.2.0 installation, reopen and rollback locally.
- [x] Build isolated Windows Studio Test 3.2.2 (run 35642029789), verify installed
  launch/local processing, stage module 1.2.0 on the test service and verify HTTPS
  update delivery, downloaded controller opening and project save/reopen.
  A module-only ZIP cannot update the shared chroma/editor/provider components.
- [ ] Owner acceptance of Studio Test 3.2.2 and auto-clipart 1.2.0: update/restart,
  real-image edges/editor/export/cleanup, then separately approved paid cycle.
- [ ] Automatic Clipart first-step feedback from owner test, 2026-09-21:
  an empty project-name field is currently saved as an empty string, so the
  project is hard to identify later. On first save, assign an editable default
  name `Клипарт — DD.MM.YYYY HH:MM` only when the owner left it blank; never
  replace a name the owner entered. Show this default in the field and use it
  consistently in saved-project and result labels.
- [ ] Automatic Clipart first-step feedback from owner test, 2026-09-21:
  move the `Выбрать папку` control onto the same row as `Рабочая папка`, at the
  right edge of the path field. Style and size it as the existing compact
  in-app folder chooser controls, not as a full-width outlined command button.
  Preserve keyboard focus, the visible full path and the native folder dialog.
- [ ] API settings feedback from owner test, 2026-09-21: change the visible label
  from `OpenRouter API Key (текстовый помощник)` to `OpenRouter API Key`.
  The parenthetical description is misleading and unnecessary.
- [ ] API settings feedback from owner test, 2026-09-21: add `Проверить баланс`
  beside the OpenRouter key, matching the other provider rows. On explicit click,
  use the entered OpenRouter key to request its available credit/balance and show
  a concise USD result or a clear invalid-key/network/provider error. Do not save
  the key merely because balance was checked; never log or display its value.
- [ ] Automatic Clipart style-step feedback from owner test, 2026-09-21: make the
  meaning of the two upper areas explicit. `Рекомендуемые базовые стили` is a
  theme-specific shortlist; `Библиотека базовых стилей` is the same single-choice
  catalogue, not a second layer of style. A selected base style must be obvious,
  and selecting another must visibly unselect the previous one in both areas.
  `Характер стиля` stays a separate, clearly labelled optional modifier layer.
- [ ] Automatic Clipart style-step feedback from owner test, 2026-09-21: replace
  the current misleading `Все` category behavior. It currently renders only six
  featured profiles out of 19 registered base styles, not every available profile.
  The owner screenshot confirms that this block has no scrollbar and the other
  13 styles cannot be reached. Add an explicit `Показать все стили` action that
  reveals the complete catalogue, keep category filters, and ensure the page has
  a visible working vertical scrollbar for the expanded list. Verify that every
  supported profile can be reached and selected. Evidence: owner screenshot
  `codex-clipboard-c328a580-d71a-40a3-8f8e-e8e5517d64da.png`.
- [ ] Automatic Clipart style-step feedback from owner test, 2026-09-21: revise
  style-card and modifier-button affordances. Inactive controls should read as
  calm, compact buttons with a subtle neutral border; only the chosen base style
  and selected modifiers use the Studio turquoise active state. Do not use the
  current blue-looking treatment that makes every option seem selected or leaves
  the click target unclear. Verify default, hover, keyboard focus and selected
  states in the real 1120x780 Windows view.
- [ ] Automatic Clipart style-step feedback from owner test, 2026-09-21: cap
  `Характер стиля` at two simultaneous modifiers. The current screen permits all
  12, producing contradictory and diluted prompt instructions. Two covers useful
  pairs such as `Нежный + Детский / nursery` and `Винтажный + Уютный` while
  retaining a clear base style. State the limit visibly as `До двух характеристик`;
  after two are selected, keep the other choices visibly unavailable until one is
  deselected. Selected modifiers use only the Studio turquoise state. Evidence:
  owner screenshot `codex-clipboard-ef4c987c-3c20-4dff-946f-c26c304abaf2.png`.
- [ ] Automatic Clipart style-step feedback from owner test, 2026-09-21: make
  `Художественная линия`, `Материал / фактура` and `Детализация` visibly normal
  single-select dropdowns, not blank text-entry-looking boxes. Default each to
  `Не выбрано`; expose the curated available choices in its menu and do not ask
  the owner to invent or type a technical style term. Keep `Базовый стиль / своя
  формулировка` as the only place where a custom style phrase is allowed. Verify
  that dropdown arrows, placeholder, selection and reset are readable at 1120x780.
  Evidence: owner screenshot
  `codex-clipboard-9e285e38-3f84-4300-917c-222f88cc75dc.png`.
- [ ] Automatic Clipart palette-step feedback from owner test, 2026-09-21: retain
  the three theme recommendations at the top, but do not silently preselect or
  apply one. They are suggestions only until the owner explicitly chooses one.
  A palette selection must be single-choice across recommendations and library:
  visibly mark the chosen card in Studio turquoise, unmark the prior card, update
  the actual palette value used by prompt generation, and expose a short selected
  name plus a clear reset action. The current click writes colors internally but
  has no visible selected state, making it appear broken.
- [ ] Automatic Clipart palette-step feedback from owner test, 2026-09-21: prevent
  palette titles and character descriptions from clipping. Long names such as
  `День святого Валентина`, `День благодарения` and `4 июля / День независимости`
  must wrap or receive enough stable card space, without truncating the beginning
  of the name. Preserve swatch visibility and the three-column layout at 1120x780.
  Evidence: owner screenshot
  `codex-clipboard-11502498-8288-483e-8cd9-3f031a689c98.png`.
- [ ] Automatic Clipart reference-step feedback from owner test, 2026-09-21:
  support drag-and-drop of PNG, JPEG and WebP reference files onto a compact,
  obvious drop target, while retaining click-to-add as an equivalent path. Replace
  the oversized empty left list with a thumbnail list/grid and compact remove
  action. Make the whole reference step fit one 1120x780 screen without requiring
  the owner to discover a second section by scrolling.
- [ ] Automatic Clipart reference-step feedback from owner test, 2026-09-21:
  remove the manual role checkboxes, free-text `Опишите нужные признаки`, palette
  extraction command, AI-planning send/no-send radio choices, privacy/preflight
  paragraphs and temporary `0 из 4` counter. They duplicate earlier choices for
  style, palette and composition or expose technical transport policy.
- [ ] Automatic Clipart reference-step product decision, 2026-09-21: an attached
  reference is automatically used as an image reference by the actual selected
  image-generation model, not sent to a separate AI object-planning request.
  The module chooses this one path without per-image participation checkboxes.
  At launch preflight, require the configured reference-capable image model and
  show a concise blocking error if unavailable; never silently drop the reference
  or fall back to a text-only model. Keep the reference locally in the project
  until the normal generation handoff, and avoid separate planner upload.
  Evidence: owner screenshots
  `codex-clipboard-7e67b1eb-7769-47a0-9032-43c4b27a2ecc.png` and
  `codex-clipboard-df2e202e-a7a1-4107-8195-3f6c0c645b0f.png`.
- [ ] Installer branding regression from owner test, 2026-09-21: the left-side
  illustration on the first Studio Test installer page still says `VIBIX Images`,
  while the window and product are `Vibix Studio Test`. Replace the embedded
  artwork/text with `Vibix Studio`, rebuild the isolated installer and inspect
  the real Windows welcome page. Evidence: owner screenshot
  `codex-clipboard-83be8f24-8e1c-4fe0-8d85-c4d8b2163a78.png`.
- [ ] Automatic Clipart object-step feedback from owner test, 2026-09-21:
  replace the current mandatory master/detail object editor with a default
  automatic bulk workflow. After theme, style, palette, references and quantity
  are set, this step must offer one clear action, `Подготовить набор`, which
  prepares every idea, title, role, pose, composition and extra detail for the
  entire requested quantity. For 100 images, batching is internal and the
  progress reports plain meaningful status such as `Подготовлено 42 из 100`;
  the owner must never fill 100 object forms. On completion, show a compact
  summary and allow going straight to prompt generation. Individual editing may
  be available behind an explicit optional `Изменить одну идею` action, never as
  the required path. Remove the initial empty labels `001 · Укажите объект`.
- [ ] Automatic Clipart object-step wording and controls, owner feedback
  2026-09-21: replace internal planning vocabulary with user-facing actions.
  The initial bulk action is `Подготовить набор`, not `Подобрать
  незакреплённые`; show `Перегенерировать эту идею` only inside the optional
  one-item editor, not beside the main action; do not expose the `закреплённая`
  concept in the normal workflow. Hide cancellation when nothing is running;
  while a request is genuinely active, label it `Остановить подбор` and state
  that an already sent paid request can still be charged. Do not show the
  provider/model selector on the normal object screen.
- [ ] Automatic Clipart planning-provider readiness, owner feedback 2026-09-21:
  choose the configured, supported text-planning route internally for the normal
  workflow and make a single paid-batch confirmation only after its availability
  and price can be established. An OpenRouter tariff lookup failure or KIE route
  that is not available must not strand the owner at a manual object form or
  make them choose a provider. If no usable route is configured, present one
  concise blocking setup message with a direct `Настройки API` action, preserve
  the project, and permit retry after setup. Never silently make a paid call,
  silently switch provider, or require manual names/actions/poses as a fallback.
  When the automatic preparation succeeds, persist generated names for all
  objects so prompt compilation never asks the owner to name every object.
  Evidence: owner screenshots `codex-clipboard-89e25148-b7b9-4f08-af89-740234b8ae95.png`,
  `codex-clipboard-3aaa3c4b-e650-451d-a7c3-f90659507830.png`,
  `codex-clipboard-919b877d-a202-40ca-b183-50eee93ba389.png` and
  `codex-clipboard-e2df4503-556a-4764-ab36-d0db69b6d6f8.png`.
- [ ] Studio home-screen feedback from owner test, 2026-09-21: rename the top
  workflow action `Сменить режим` to `Главная Studio` and make it open a real
  Studio home screen rather than a catalogue-only page. The home screen must
  place `Продолжить работу` first and show the three most recently saved
  projects, with their project name, module, last-change date and a concise
  saved state (for example, draft or prompts prepared); clicking one resumes it
  with its saved intermediate data. Provide `Все проекты` for the full list.
  Keep the module catalogue below this useful work area, and remove the
  redundant full-width `Вернуться` command.
- [ ] Studio home-screen feedback from owner test, 2026-09-21: add a compact
  `Новости Studio` block to the home screen. It should show actual Studio/module
  release notes and update availability from trusted signed update metadata,
  not invented generic news; when no new item is available, state the installed
  versions succinctly. Keep the existing module-update dialog as the detailed
  update action.
- [ ] Installed Auto Clipart card regression from owner test, 2026-09-21: the
  signed Auto Clipart 1.2.0 module was installed through the Studio Test update
  flow, but its catalogue card shows disabled `Купить` instead of `Открыть`.
  Reconcile the trusted installed-module registry, active test-license
  entitlement and catalogue availability before rendering the card, then retain
  the runtime authorization check on click. A valid installed-and-entitled
  module must show `Открыть`; an update must show `Обновить`; a copied or
  unentitled package must remain non-openable. Do not represent an entitlement
  lookup failure as an invitation to buy. Add regression coverage for the real
  signed-install/update path and inspect the Windows screen after rebuilding.
  Evidence: owner screenshot
  `codex-clipboard-ee26fcd0-fb6f-4adb-94b1-cd4619b42539.png`.
- [ ] Implement the acceptance corrections in dependency order: resolve trusted
  availability and planning readiness contracts, obtain required visual approval
  for revised home/builder states, then wire the automatic workflow and verify
  native Windows acceptance. New UI requirements do not count as approved mockups.
- [ ] Catalogue acceptance matrix: signed installed/entitled, entitled/not
  installed, revoked/expired, unknown/failed entitlement lookup, tampered package,
  incompatible shell, compatible signed update, restart and offline grace. Unknown
  rights must neither grant access nor become `Buy`; check exact `auto-clipart`
  rights and current trust at every open/download/update boundary. An available
  compatible update must not prevent opening the valid installed version.
- [ ] Reference handoff contract: carry attachments through saved recipe, prompt
  entries and the actual image-provider adapter; send no images to text planning.
  Keep one-shot disclosure/consent in the normal generation confirmation, bind it
  to exact file bytes and route, enforce the selected endpoint's real limits and
  block missing/changed/unsupported files. Removing role/privacy controls must
  not authorize an upload on attach/save/reopen. Preserve legacy reference data.
- [ ] Automatic planning acceptance: 100 targets use the existing <=80 sequential
  batching with one total estimate/confirmation, validated progress and atomic
  application. Cover second-batch failure, cancel, stale brief, malformed response,
  duplicate/missing IDs, preserved manual edits and saved-plan reopen. No hidden
  paid readiness probe, retry, provider switch or PNG generation; a new paid
  attempt requires new consent. Persist successful names before prompt handoff.
- [ ] Style/palette acceptance: changing recommendations/categories never changes
  the selection implicitly; reset and save/reopen preserve the actual prompt
  inputs. Old recipes with more than two modifiers retain their saved data and
  ask for a valid selection before a new plan/prompt instead of silent truncation.
- [ ] Home acceptance: 0/1/2/3+ projects, save-time ordering, full-list access,
  resume without paid work, save failure and unavailable module; signed news,
  offline/error versus no update, and safe plain-text notes. News failure must not
  block local work. Final checks require 1120x780 Windows views and the signed
  installed/update path; source/offscreen checks alone do not close acceptance.
- [x] Implement bounded provisional-rim reclassification with same-object
  references and small-island protection; persist reproducible visual reports.
- [x] Fix source-RGB restoration reintroducing a cleaned opaque rim; retain only
  bounded edge-connected key-mixture corrections, with v4 provenance and tests
  for three key colours, protected interior details and unchanged delivery pixels.
- [x] Add bounded opaque AA-edge colour/alpha reconstruction, v3 provenance and
  explicit app-profile benchmark; preserve opaque interior and legacy behaviour.
- [ ] Remaining edge quality: contaminated fully opaque rims, isolated thin-detail
  references and real final-PNG acceptance after upscale; v3 is partial progress.
- [x] Add separate default-off export cleanup choices for intermediates and
  generated originals; verify ZIPs first and delete only hash-bound owned copies.
  Preserve legacy/untracked files and unfinished or excluded images.
- [x] Soften final-upscale checks: keep unexpected-size output with a warning;
  retain lost-alpha output for correction, with bundle export blocked by alpha QC.
  Empty/corrupt output fails only that item, without automatic paid retries.
- [x] Validate actual final upscale dimensions and retained/nonempty alpha;
  publish the locally checked bytes rather than downloading the result twice.
- [x] Rerun six-case synthetic removal benchmark and inspect contact sheet.
- [x] Verify final-upscale guard: full offline suite 1693 passed, 57 skipped,
  18 deselected, 262 subtests; affected suite 18 passed plus 15 subtests.
- [x] Reinforce opaque-only subjects in planning and RU/EN object prompts,
  including watercolor. Translucent materials are outside automatic Clipart scope.
- [ ] Resolve colour residue on opaque subject boundaries under the existing
  Chroma quality task; real provider upscale acceptance remains open.

2026-09-20 source follow-up: automatic launch now offers provider/model/scale for
one alpha-safe post-background upscale, retains it across reopen, and validates
the actual Fal model before launch. Current source is newer than installer 3.2.1.
Qt/OpenCV environment is available at `/tmp/vibix32-venv/bin/python`.
Full offline verification: 1692 passed, 57 skipped, 18 deselected and 250 subtests
passed. Actual provider quality and updated Windows packaging remain open.

Owner requested development now; previous Windows owner acceptance stays open
but no longer gates this independent implementation. Ordinary generation must
not offer collection planning or bundle tools.

- [x] Separate module identity from reusable legacy state scope in Core/host.
- [x] Preserve automatic project identity and block cross-module relabeling;
  verify recipe save/reopen and exact entitlement/revocation without paid calls.
- [x] Remove builder entry and collection export from ordinary generation;
  retain legacy metadata/edited-output compatibility and individual image tools.
- [x] Label the ordinary workflow `Генерация изображений`; verify 1120x780 Qt view
  and fix stale sidebar-label overlap.
- [x] Implement separate automatic controller, eight-step navigation and resume
  keyed by project envelope module ID, not its reused legacy state mode.
- [x] Connect recipe/style/palette/references/structure/objects to prompt preview,
  explicit cost-confirmed run, Review and per-set export.
- [x] Verify local automatic workflow with mocked paid worker, real fixture PNG,
  ZIP/PDF export, edited-result restoration and exact rights; gated source catalogue.
- [x] Extend signed package inventory/delivery to automatic Clipart; verify real
  loopback HTTPS download, signed runtime load, update/rollback and exact rights.
- [x] Authorized isolated Windows 3.2.1 build and installed automated acceptance;
  run 35465131655, source 7dd7c99; verified installer/private owner kit downloaded.
- [x] Test server: four packages 1.1.0 for Studio >=3.2.1, automatic rights on
  two expiring test licenses, backup and external HTTPS/runtime checks passed.
- [ ] Owner Windows installation/activation and separately budgeted live provider
  smoke. No paid generation or production publication performed.

Detailed current evidence and next-step constraints are at the top of STATE.md.

## Stability And Lightweight Studio, 2026-09-20

Goal: keep Studio as a reliable shell, make expensive local tools optional, and
reduce installation/startup cost without weakening project recovery, package
signatures or offline image-processing capability.

### Phase 1: Measure Before Changing Packaging

- [ ] Produce a reproducible size inventory for the Windows installer and the
  unpacked application: Python/Qt, local background removal, ONNX models,
  Real-ESRGAN, assets and each bundled workflow.
- [ ] Measure cold startup time, first-open time for each mode and idle memory on
  Windows Test and macOS; publish the environment and measurements with results.
- [ ] Identify imports and initialization that happen before a user opens local
  processing; add regression checks so a non-processing workflow does not load
  models or start a model download.

### Phase 2: Optional Local Processing Payload

- [ ] Define a signed, platform-specific optional payload contract for local
  background removal and upscale. It must support Windows, macOS Intel and
  macOS Apple Silicon separately where binary files differ.
- [ ] Keep the base Studio capable of opening projects and using remote image
  generation without local ML payloads. Show one clear install action when a
  user explicitly chooses a local operation.
- [ ] Download optional payloads only after explicit user action, display size,
  transfer progress and verification, and retain a completed verified payload
  for offline reuse. Never hide a provider or model download behind a paid run.
- [ ] Make payload install/update transactional with checksum/signature checks,
  cancellation, resume/retry rules and a safe previous-version fallback.
- [ ] Verify uninstall/cleanup removes only optional caches, never projects,
  exported PNGs, credentials or installed workflow packages.

### Phase 3: Reliability And Recovery

- [ ] Add fault-injection coverage for application termination, internet loss,
  disk-full and permission errors at project save, provider submission, result
  publication, module update and optional-payload update boundaries.
- [ ] Audit durable run records so every paid submission has an idempotency or
  recovery state before sending; after restart, require explicit confirmation
  before any retry that could incur another charge.
- [ ] Add a visible recovery centre for incomplete local work: saved project,
  completed files, failed local step and a safe next action. It must not expose
  credentials or full local paths in diagnostics.
- [ ] Define and test cache limits, low-disk warning thresholds and an explicit
  cache-management screen with a size preview before deletion.

### Phase 4: Release Confidence

- [ ] Run the same optional-payload, recovery and update matrix on Windows and
  both macOS architectures before declaring cross-platform compatibility.
- [ ] Compare final installer size, startup and memory against the Phase 1
  baseline. Keep the old packaging if measurements do not show a meaningful
  improvement or recovery guarantees weaken.

Decision rule: do not split existing workflows merely because their code is
small. Split only heavyweight platform-specific processing payloads after the
measurement baseline confirms the benefit.

## Isolated Acceptance, 2026-09-19

- [x] Owner delegated recommended test Windows/server setup; no production release.
- [x] Separate build-time trust, app data, installer AppId/name and overwrite guard.
- [x] Deploy separate test database/API, expiring test licenses and signed test modules.
- [x] Verify real external HTTPS activation/download/install for all three modules.
- [x] Run Windows acceptance build, native security/installer guards and installed smoke.
  Run `35443570132`, source `47fe5a2`, downloaded SHA/provenance verified.
- [x] Prepare test installer and private owner kit with short acceptance instructions;
  no private keys or test license contents enter Git, public artifacts or logs.
- [ ] Owner Windows activation, three module updates with progress, opening/restart
  acceptance using `docs/testing/module-delivery-windows-acceptance.ru.md`.

## Independent module updates, 2026-09-19

Owner priority: preserve and connect the existing image generation, processing,
and Pinterest first; then deliver the separate automatic Clipart workflow.
Existing generation retains the legacy `clipart` identity for saved projects and
license rights. Future automatic Clipart uses `auto-clipart` and remains unreleased.

- [x] Verify real existing home cards, controller admission, exact module rights,
  revocation, and saved-project resume without automatic work (7 integration tests).
- [x] Publisher preparation API: explicit payload, signature, client-compatible verification.
- [x] Verify generated package install/update/rollback and user-data preservation (43 tests).
- [x] Bind staged package identity to the selected module/version before writes; 49 affected tests pass.
- [x] Server module-release API/private delivery, with exact rights on manifest/download;
  migration 012 tested on disposable PostgreSQL, not deployed.
- [x] Connect installed signed workflow packages to real Studio controller launch;
  verify HTTPS download/install/update/rollback/project preservation for all three flows.
- [x] Official workflow inventory packaging API and CLI; no manual ZIP assembly.
- [x] Base module-update layout accepted with corrections: no future-module footer;
  visible transfer percent/MB and indeterminate checking/verification indicators.
- [x] Connect corrected user-facing update controls with background progress,
  exact rights, signature verification, activation and error preservation.
  9 HTTPS/Qt scenarios pass; production download stays disabled without trust keys.
- [x] Admin module-release UI: shell/module fields, compatibility, private ZIP,
  type/search filters, serialized draft creation and recoverable upload errors.
  Matching service branch remains undeployed.
- [x] Controlled official release-set preparation and verified HTTPS admin draft
  upload; metadata/bytes checked, no automatic publish or retry.
- [x] Provision dedicated publisher key outside Git and pin its public half in
  candidate shell; prepare verified 1.0.0 workflow artifacts for Windows/macOS.
- [ ] Verify off-host publisher key recovery custody before production publication.
- [ ] Full installed Windows acceptance and separately authorized desktop release.
- [x] Align Azure default with release 3.2.0, without launching a build;
  full isolated pytest: 1640 passed, 57 skipped, 14 deselected.

Separate automatic Clipart next-slice constraints (read-only audit):
`v3_clipart_flow.py` currently opens `ClipartBuilderDialog` inside legacy
`clipart`; this is not a separate released module. Before routing catalog
`auto-clipart`, separate workflow/license/project identity from the reusable
legacy state scope in `_studio_workflow_core.py`, `studio_workflow_host.py` and
`V3ProjectDocumentAdapter`. Do not rename legacy projects or infer auto access
from `clipart`. Preserve shared planner/recipe/objects/bundle/export services,
and use the eight-screen PRD, not the superseded six-screen proposal.
Deliver and verify the existing workflows first, as requested by the owner.

## Preparation gate before new implementation

- [x] Reproduce and fix review P2s: contour copy to current result/export,
  schema-aware membership path validation, bounded undo history predecessor.
- [x] Focused regression: 211 passed, 14 subtests; no wording-only tests added.
- [x] Full offline pytest: 1361 passed, 57 skipped, 2 deselected, 223 subtests;
  compilation, startup smoke, tracked artifact guard and diff-check passed.
- [x] Socket recheck through orchestrator escalation: 2 tests OK, exit 0 (0.204s).
- [x] New independent review: no findings in fixes/integration scope;
  reviewer independently ran 93 tests and 8 subtests.

Verification gate is complete. Preservation commit `40ceffa` was sent and
verified previously. This does not complete Studio 3.2. The many-to-many
membership migration has since been started partially in a local working copy,
but remains open and stopped before independent review, any required fixes,
commit/push, and a clean `git status`.

## Owner refinement recorded; stop after documentation

Pending next implementation: automatic overlapping mini/standard/maxi/full-bundle
plans before generation, many-to-many asset membership with safe migration of the
current single assignment, reuse one processed PNG across ZIPs without repeat cost.
Manual assignment becomes an optional editor; default path is review/correct only.
Expand categorized palette cards and brief-based recommendations (holidays,
seasons, nature incl. mountains/sand/clay, color families, use cases).
Remove background-removal method names/key colors from ALL user-facing surfaces,
including settings/help/errors/user diagnostics and delivery metadata; keep
internal checks and generation model/cost visibility. See latest PRD section.

This documentation checkpoint does not close the stopped implementation copy.
After resumption, finish and review many-to-many first; only then continue the
remaining open tasks in order. Existing runtime is not yet compliant with these
latest requirements.

## Current stopped many-to-many working copy

The working tree is intentionally dirty from the stopped subtask. It currently
touches `studio_export_membership.py`, `studio_projects.py`,
`studio_set_export_ui.py`, `v3_project_state.py`, `v3_run_queue.py` and related
tests, including the new `tests/test_studio_export_membership.py`. These are
unfinished local changes, not a release or a completed task. Do not mark the
many-to-many items below as done until independent review, required fixes,
commit/push and clean status are complete. Do not include these files in this
documentation commit.

## Result export now connected

Clipart results now open explicit set membership / PNG inclusion / review dialog.
Threaded export creates separate ZIPs with PNGs and PDF; cancel cleans staging.
Only successful final PNGs of the current session are offered; no folder guessing.
Membership now saves via the project draft and restores titles/exclusions across
reopening, without restoring the review checkbox. Older-run assignments survive.
Next: reference-image analysis and integrated alpha/QC. Packaging checkbox does
not certify cutout quality. See STATE.md tests and the saved Qt screenshot.

## Planning UI connected; export core implemented

- Done: OpenRouter key/settings, recipe provider/model persistence, async builder
  planning with current-tariff confirmation, cancel/stale guards and no auto retry.
- Done: explicit multi-set export API, one ZIP per set with overview PDF and PNGs,
  staged publication and unchanged source PNGs.
- Pending: KIE tariff/launch gate, real image-reference analysis, paid live probes
  (new budget required), integrated QC and set-membership/export UI.
- Not complete: full Studio workflow, Patterns/Junk Journal and release acceptance.

See STATE.md for precise limits: OpenRouter key uses local plaintext .env like KIE;
estimate is not a monetary cap; archive API is not yet exposed on results screen.

## Text assistant routes implemented, UI pending

Approved KIE + OpenRouter and Gemini 3.8 Flash / DeepSeek V4 Flash Vision Exp /
GPT-5 mini. Added explicit provider catalog and single-request planner adapter.
Next: secure OpenRouter credential/settings integration, asynchronous builder
actions with cost/consent preflight, then separately authorized live probes.
No live requests, automatic fallback or image-reference upload in this increment.
The adapter alone does not complete the automatic-planning user workflow.

## Automatic planning priority

Owner approved brief-driven AI set proposals with optional manual edits.
Implemented offline planning request/atomic response validation, pin persistence
and editor control. Next: verified text provider adapter and explicit planning
actions, then end-to-end prompt/background-review/export integration. No live
AI planning is connected yet; see VS-13/15 and STATE.md for actual status.

## Concrete objects increment

Object editor and optional append-to-prompts now work through existing draft
storage and prompt generation. Recipe slots preserve manual details; names are
required for prompt handoff. Next: semantic/reference integration, full module
processing preflight and independent set exports. See STATE.md for limits/tests.

## Reference increment

Separate reference page and explicit local palette extraction are implemented.
Roles and manual observations survive draft reload; source files are preserved.
Next: region selection/portable references, automatic semantic analysis when its
provider is selected, concrete objects and prompt handoff. No paid calls made.

## Latest UI increment

Working Clipart-only set-settings dialog: idea, visual direction/palettes,
editable recipe. Saves through the existing project draft; cancellation keeps
state unchanged. Owner authorized coding the described workflow. Next integrate
the separate reference step, concrete objects and prompt handoff, then delivery.
The full eight-screen flow is still incomplete; see STATE.md for verification.

## Latest implementation: editable Clipart recipes

VS-13 now has offline balanced/characters/decorative recipes for 1–1000 images,
exact totals, explicit manual role edits, and optional validated persistence in
the existing V3 project draft. Theme, custom context and related motifs survive
save/reopen. Legacy drafts remain valid. This is the planning data layer;
the eight-screen builder, reference analysis, prompt handoff and per-set ZIP
integration remain open. See STATE.md for verification.

## Current priority: separate application modules

Owner rejected the mixed result-kind review UI. Clipart, Patterns and Junk
Journal have separate entry points/screens/workflows. Internal result_kind
guards remain; no cross-module user dropdown. Next approve the Clipart-only
proposal in docs/ui/3.2/clipart-review-proposal/, implement its module-specific
review/preflight, and complete existing-image quality acceptance. Then Patterns;
Junk Journal remains its own future module. Old mixed UI tasks below are history.

## Result-kind routing increment, 2026-09-10

Explicit per-prompt type now survives project/edit/queue/retry. Surface types
skip remover, edge shrink and trim, with per-type removal cost quantities.
Legacy inputs are unchanged; this does not infer types from prompt text.
Next: approved type/profile UI and matching stage/provider preflight, portable
PNG type metadata, then hole-policy validation. See VS-15/17 checkpoint in
TASKS_VIBIX_STUDIO_3.2.ru.md. No new paid generation or build.

## Attachment follow-up, 2026-09-10

Latest: owner raised the key cap; four GPT Image 2 probes completed, $0.12 total
spent of $1. RGBA output confirmed for transparent prompts, but wreath haze
remains; current chroma is primary pending broader QC. Key retained outside
project, mode 0600, at owner's request. Earlier key-cap blocker below is history.

Owner authorized documentation, offline comparison and continued implementation.
Initial code-433 key-cap failures are resolved; see STATE.md for attempt history.
Use the new priority checkpoint in TASKS_VIBIX_STUDIO_3.2.ru.md. The ZIP
candidate failed existing reference cases and is not integrated. Existing
native-alpha reuse is strengthened; native-generation provider integration,
full QC, white removal and real-image acceptance remain open. Owner subsequently
authorized up to $1 total for KIE comparison. Spend is $0.12, remaining $0.88;
key retained outside project. Build/publication remain separate.

Material review is complete: text dialogue/research, six screenshots and three
spreadsheet builders. Accepted: shared Holiday/character profiles, presets,
palette sources and distinct multi-detail/variant modes; no Midjourney addition.
New bounded VS-16 increment: persist requested chroma before generation and bind
it to raw-image SHA256; reuse on local reprocessing. Automatic per-prompt
selection/queue handoff already existed (previous status corrected).
Next: approve the builder mockup; complete Job/Attempt/observed-background
metadata and validate a small Clipart → review/editor
→ PNG set using existing images first. Patterns follows; Nano Banana Pro is a
tile-generation candidate, SeedVR2 Seamless a separate optional upscale candidate.
Junk Journal is approved as a separate future module; Alphabet remains future
scope. Original PNGs, not screenshots, are
 needed for cutout acceptance. Clipart starts from an editable role-based set
 recipe (hero objects, compositions, wreaths, borders/frames, small decor) and
 ends with an overview sheet plus a ZIP of Ready PNGs. See VS-13–18/26/28/31/34
 in the 3.2 tasks.
No full Studio completion claimed. No new paid generation or build.

## Active branch: Studio 3.2

Current work runs in `codex/feature-alpha-routing-benchmark-3.2` in the
same `studio-3.2-worktree`, based on the existing develop/3.2 working state.
Explicit opaque clipart processing now has reference colour/geometry metrics
and final-export hash-bound processing receipts. Opt-in completed-stage tracing
is available; opaque profile v2 omits the translucent-material recolouring
heuristic while retaining legitimate opaque colours and legacy behavior.
An additional ordinary-AA
prototype was rejected after thin-detail regressions; this quality gap remains
open. Next algorithm work must pass all six independent reference fixtures,
not only the 39 selector probes. Full CK-01…11 scope remains open
(PRD_CHROMA_KEY_QUALITY_V1.ru.md).

Direct upstream execution now supplements the audit: six goldens, three narrow
AA squares and one separate opaque island. Adaptive rim checking is promising
but not sufficient; upstream defaults fail some preservation cases. Next work
must test pre-solve classification/reference confidence against these cases;
do not introduce global island deletion. See the existing full audit for evidence.

The owner authorized the new implementation. Current ordered scope/progress is
in `TASKS_VIBIX_STUDIO_3.2.ru.md`; specification is
`PRD_VIBIX_STUDIO_3.2_V2.ru.md`. The 3.0 release tasks below are historical,
not authorization to build or publish Studio 3.2. Home direction approved:
three recent projects plus equal illustrated cards. Separate project autosave,
resume and illustrated catalog are connected. Catalog download/purchase intents
are not production integrations; portable assets, runtime pages and editors remain open.
Task journals now use each Studio project's UUID and save-before-worker boundary;
durable run recovery and unknown paid POST outcomes remain open (see 3.2 tasks).
Contour dialog is now connected from transparency editing, with fixed brush
presets, mouse/keyboard control, alpha-only history and separate PNG export.
VS-19/20/21 remain partial: node add/delete, edit-history persistence, QC and
large-image background extraction remain open; no packaged acceptance yet.

Source specs: `PRD.md` and `PROCESSING_PIPELINE_TZ.md`.

Rule: take the next open task in order. Keep code changes narrow and do not refactor working code unless it directly makes the current task safer.

For each task: explain the plan, implement only that task, verify it, update `TASKS.md` and `CHANGELOG.md`, then commit and push. Ordinary pushes must not start a build or release workflow. Build, tag, publish, release, and manual GitHub Actions runs are allowed only after an explicit user command that the application is ready.

Current next task: **Run owner acceptance on the replacement Windows 3.0.5
installer from GitHub Actions run `33032049521`. Do not upload a server revision
before this target-Windows acceptance.**

## Phase 1 - Preparation

- [x] Add `realesrgan-ncnn-vulkan-20211212-windows/` to `.gitignore`.
- [x] Add new default config keys in `main.py`.
- [x] Verify old config files still open without errors.

## Phase 2 - UI

- [x] Add upscale provider selection: `KIE` / `Local Real-ESRGAN`.
- [x] Add Local Real-ESRGAN settings: folder path, profile, scale.
- [x] Add background removal provider selection: `KIE` / `Local rembg`.
- [x] Add Local rembg settings: profile/model.
- [x] Add separate `Удалять контур` checkbox and `1/2/3 px` selector.
- [x] Wire new UI fields into settings save/load.

## Phase 3 - Local Real-ESRGAN

- [x] Validate path to `realesrgan-ncnn-vulkan.exe`.
- [x] Run Real-ESRGAN through `subprocess.run`.
- [x] Save Real-ESRGAN output into `raw/`.
- [x] Log the local upscale step without secrets or noisy command dumps.
- [x] Handle errors: missing exe, missing models, failed process, missing output file.

## Phase 4 - Local rembg

- [x] Import `rembg` lazily so the app can still start if model setup is not ready.
- [x] Create `new_session()` once per batch.
- [x] Implement local background removal for one file.
- [x] Save local rembg output as PNG with alpha.
- [x] Log clearly that the first model run can take longer.

## Phase 5 - Edge Shrink

- [x] Implement `shrink_alpha_edges`.
- [x] Run edge shrink after background removal.
- [x] Allow edge shrink without background removal when input already has alpha.
- [x] Clamp edge shrink pixels to `1..3`.

## Phase 6 - Pipeline Integration

- [x] Preserve current KIE-only behavior.
- [x] Support local-only processing without requiring KIE API Key.
- [x] Support mixed local -> KIE and KIE -> local flows.
- [x] Update `needs_kie_api` so KIE API Key is required only when a selected step actually uses KIE.

## Phase 7 - Documentation

- [x] Link `PROJECT_KNOWLEDGE_BASE.md` or a project page to `PROCESSING_PIPELINE_TZ.md`.
- [x] Add a short author instruction for Real-ESRGAN + rembg + edge shrink settings.

## Phase 8 - Verification

- [x] Run `python -m py_compile .\main.py`.
- [x] Test one image through local-only pipeline.
- [x] Test one image through mixed pipeline.
- [x] Inspect output on a dark background.
- [x] Verify Real-ESRGAN binaries/models are not tracked by git.

## Phase 9 - Local rembg Settings

- [x] Add a local rembg edge quality setting with `Soft`, `Normal`, and `Sharp` presets.
- [x] Save and load the local rembg edge quality setting with the rest of the UI config.
- [x] Apply local rembg edge quality only after local rembg output, without changing KIE behavior.
- [x] Verify the new setting with a targeted smoke test.

## Phase 10 - Fixed Processing Order and Unsharp Mask

- [x] Add optional Unsharp Mask settings after upscale.
- [x] Allow custom Unsharp Mask amount, radius, and threshold values.
- [x] Fix processing order to `upscale -> unsharp -> remove background -> edge shrink -> trim`.
- [x] Remove the trim timing selector from the UI and config writes.
- [x] Verify compile, Unsharp Mask output, and a mixed pipeline smoke test.

## Phase 11 - Processing UI Order

- [x] Reorder the processing controls vertically to match the actual processing order.
- [x] Move each action's parameters to the right of that action.
- [x] Verify UI construction and settings save/load.

## Phase 12 - Processing UI Polish

- [x] Make Unsharp Mask independent from the upscale checkbox.
- [x] Keep the edge contour pixel selector compact.
- [x] Fix processing provider settings layout so price labels and rembg model fields do not overlap.
- [x] Verify UI construction, settings save/load, and Unsharp Mask without upscale.

## Phase 13 - Provider Settings UI Cost Labels

- [x] Move KIE processing cost labels next to their model selectors.
- [x] Keep the provider settings grid compact without overlapping rembg fields.
- [x] Verify UI construction and settings save/load.

## Phase 14 - Inline Processing Cost Labels

- [x] Put each KIE processing cost label in the same row widget as its model selector.
- [x] Verify UI construction and settings save/load.

## Phase 15 - BEN2 Evaluation Script

- [x] Add a standalone BEN2 background removal test script.
- [x] Document the exact command to install and run BEN2 testing.
- [x] Verify the script compiles and exposes help without requiring BEN2 to be installed.

## Phase 16 - Local BEN2 Provider

- [x] Add Local BEN2 as an experimental background removal provider.
- [x] Add BEN2 hard alpha threshold, edge softness, and corner radius settings.
- [x] Keep BEN2 default output hard-edged with no semi-transparent alpha.
- [x] Save and load BEN2 settings with the rest of the processing config.
- [x] Let local BEN2 processing run without requiring a KIE API key.
- [x] Verify compile, UI settings save/load, and hard-alpha post-processing.

## Phase 17 - Local Real-ESRGAN Scale Fix

- [x] Diagnose square/tile artifacts in Local Real-ESRGAN `2x` output.
- [x] Use a scale-compatible Real-ESRGAN model for `Clipart 2x`.
- [x] Keep Local Real-ESRGAN `2x` and `4x` available in the UI.
- [x] Remove unsupported local `3x` from the scale selector.
- [x] Verify compile and local command/model selection smoke tests.

## Phase 18 - Local Real-ESRGAN Alpha Preservation

- [x] Diagnose fully transparent output when upscaling an already-trimmed RGBA PNG.
- [x] Run Local Real-ESRGAN on a temporary RGB composite when the input has alpha.
- [x] Restore the upscaled alpha channel after Local Real-ESRGAN finishes.
- [x] Verify compile and a real Local Real-ESRGAN run on the affected bird PNG.

## Open Tasks - Execute In Order

## Task 19 - Automated MVP Baseline

Status: Done

Goal:
Prove that the current application starts and accepts old settings before adding another processing feature.

Steps:
- Compile and import `main.py`.
- Construct `MainWindow` in Qt offscreen mode.
- Load an isolated legacy config with the newer processing keys omitted and verify safe defaults.
- Fix only blocking regressions discovered by these checks, then rerun the same checks.

Acceptance:
- [x] The module compiles and imports without errors.
- [x] The main window constructs without changing the current UI layout.
- [x] Existing config files remain compatible and missing keys receive defaults.

Verification:
- [x] `python -m py_compile .\main.py`
- [x] `$env:QT_QPA_PLATFORM='offscreen'; python -c "import main; app=main.QApplication([]); w=main.MainWindow(); print('SMOKE_OK')"`
- [x] Isolated legacy-config smoke returned `LEGACY_CONFIG_OK` without reading or changing the user's real config.

Notes:
- Do not use the user's real config or print stored keys.
- No build or release work belongs to this task.

## Task 20 - Local Processing Acceptance

Status: Done

Goal:
Verify the main process-only workflow without KIE and prevent recurrence of the alpha and tiled-upscale regressions.

Steps:
- Add reusable owned RGB and RGBA test fixtures or generate synthetic fixtures during the test.
- Test Local Real-ESRGAN at `2x` and `4x`, including exact dimensions and restored alpha.
- Test Unsharp Mask, Local rembg/BEN2, hard alpha, edge shrink, trim, `raw/`, and final `output/` in pipeline order.
- Inspect one transparent result on a dark background.

Acceptance:
- [x] Process-only local mode works without a KIE key.
- [x] `2x` and `4x` outputs have correct dimensions without tile artifacts.
- [x] Transparent PNG output is non-empty and keeps a valid alpha channel.
- [x] The final order remains `upscale -> unsharp -> remove background -> edge shrink -> trim -> save`.

Verification:
- [x] `python -m unittest tests.test_local_processing_acceptance -v`
- [x] Manual dark-background comparison is recorded in `CHANGELOG.md`.

Notes:
- Use the existing local Real-ESRGAN folder; do not add its binaries or models to git.

## Task 21 - KIE And Mixed Workflow Acceptance

Status: Done

Goal:
Confirm API-key routing and the generation/mixed workflows without changing provider behavior.

Steps:
- Test key validation for local-only, KIE-only, and mixed selections without making network calls.
- Run one minimal generate-only check and one mixed processing check when a valid KIE key is available.
- Verify progress messages, `raw/`, `output/`, and error handling without logging secrets.

Acceptance:
- [x] Local-only mode never asks for a KIE key.
- [x] KIE-only and mixed modes request the key only when a selected step uses KIE.
- [x] Generate-only and mixed workflows save the expected files.
- [x] No API key or secret appears in logs.

Verification:
- [x] `python -m unittest tests.test_kie_routing -v`
- [x] Live KIE smoke was not run to avoid consuming credits; network-free generate-only and mixed-flow tests were used instead.

Notes:
- A live check can consume credits; keep it to the smallest useful sample.

## Task 22 - MVP Acceptance Closeout

Status: Done

Goal:
Close the current MVP against the product documents before starting post-MVP cleanup features.

Steps:
- Review `README_AUTHOR_SHORT.md`, `PRD.md`, `TASKS.md`, `CHANGELOG.md`, and `TEST_CHECKLIST.md` against the verified behavior.
- Complete the non-release sections of `TEST_CHECKLIST.md`.
- Fix only blocking issues; record non-blocking improvements as later tasks.
- Update PRD acceptance checkboxes only where evidence exists.

Acceptance:
- [x] Every MVP acceptance criterion is either verified or explicitly reserved for the release checklist.
- [x] Documentation matches the actual UI and processing order.
- [x] No build, release, tag, or update-repository action is performed.

Verification:
- [x] `python -m py_compile .\main.py`
- [x] `python -m unittest discover -s tests -v`
- [x] Manual and automated main-flow evidence is recorded in `CHANGELOG.md`.

Notes:
- Closed with 14 passing tests. Live KIE and release-only visual/build checks remain intentionally open until an explicit release request.

## Task 22A - GPT Image 2 KIE Model Routing Hotfix

Status: Done

Goal:
Restore GPT Image 2 generation in the current application without importing release-only changes from the 1.0.3 hotfix branch.

Steps:
- Keep the UI/config model id as `gpt-image-2`.
- Route KIE requests without references to `gpt-image-2-text-to-image`.
- Route KIE requests with references to `gpt-image-2-image-to-image`.
- Apply the same routing to model availability probes and normalize saved endpoint ids back to the UI id.
- Add network-free regression tests for both routes.

Acceptance:
- [x] Text-to-image and image-to-image requests use the documented KIE model ids.
- [x] The visible model name and saved config remain compatible with `gpt-image-2`.
- [x] Other generation models are unchanged.

Verification:
- [x] `python -m py_compile .\main.py`
- [x] `python -m unittest tests.test_kie_routing -v`
- [x] `python -m unittest discover -s tests -v`

Notes:
- Live KIE generation is excluded from this task to avoid consuming credits; the same routing was previously verified live in the isolated 1.0.3 hotfix.

## Task 22B - PhotoRoom Standard Background Removal

Status: Done

Goal:
Add PhotoRoom Standard as an independent background-removal provider without changing existing provider behavior.

Steps:
- Add a separate masked PhotoRoom API key field and lock in Settings.
- Add `PhotoRoom Standard` to the background provider selector.
- Send local image files to the documented `/v1/segment` endpoint as PNG/RGBA/full-size output.
- Validate the returned image before saving it into `raw/`.
- Require only the key for the provider actually selected and keep secrets out of logs.

Acceptance:
- [x] PhotoRoom Standard can be selected independently from KIE, rembg, and BEN2.
- [x] Process-only PhotoRoom does not require a KIE API key.
- [x] A missing PhotoRoom key or invalid response produces an actionable error.
- [x] The PhotoRoom key and provider selection save and restore safely.
- [x] Existing providers and processing order remain unchanged.

Verification:
- [x] `python -m py_compile .\main.py`
- [x] `python -m unittest tests.test_photoroom_provider -v`
- [x] `python -m unittest discover -s tests -v`

Notes:
- Standard mode uses `https://sdk.photoroom.com/v1/segment`; no paid live request is required for automated verification.
- Verification passed with 4 focused PhotoRoom tests and 20 tests in the full suite; no live PhotoRoom credits were spent.

## Task 22C - Upscale Before And After Background Removal

Status: Done

Goal:
Allow upscale before background removal, after background removal, or at both positions.

Steps:
- Replace the single upscale step with independent before/after controls.
- Give each enabled pass its own provider and `2x/4x` scale settings.
- Preserve current behavior for old configs: before enabled, after disabled.
- Show the combined multiplier when both passes are enabled.
- Keep edge cleanup and trim after the final upscale pass.

Acceptance:
- [x] Before-only, after-only, and both-pass pipelines run in the selected order.
- [x] `2x + 2x` produces `4x`; `4x + 4x` clearly reports `16x` before processing.
- [x] Transparent PNG alpha remains valid after a post-removal upscale.
- [x] Existing configs retain their current before-upscale behavior.

Verification:
- [x] `python -m unittest tests.test_upscale_positions -v`
- [x] `python -m unittest discover -s tests -v`

Notes:
- Verification passed with 4 focused tests and 24 tests in the full suite. The Settings layout was also rendered offscreen at `1100x900` without control overlap.

## Task 23 - Cleanup Capability And Safety Matrix

Status: Done

Goal:
Define exactly what can be inspected or removed reliably before adding cleanup controls.

Steps:
- Research current official documentation for Nano Banana/Gemini marks, standard image metadata, provenance manifests, and pixel-level hidden markers.
- Separate four categories: ordinary metadata, AI/service metadata, embedded provenance manifests, and pixel-level watermarks.
- Define supported input/output formats and ownership/licensing limits.
- Decide which actions can be labelled `remove`, which are only `detect/report`, and which are unsupported.

Acceptance:
- [x] A durable capability matrix lists supported, detectable-only, and unsupported items.
- [x] Every factual claim has an official or primary source.
- [x] The plan does not promise reliable removal of unknown pixel-level markers.

Verification:
- [x] The capability matrix is linked from `PRD.md` and `PROJECT_KNOWLEDGE_BASE.md`.

Notes:
- This research task must finish before implementation choices are locked.
- Decision: file metadata can be inspected and selectively removed; embedded C2PA removal is narrowly scoped to the new export and requires fixture validation; pixel-level markers may use a separate experimental whole-image regeneration mode but are not metadata-removal features.
- Candidate review: `lana-info/remove-ai-watermarks` is Apache-2.0 and suitable for a local prototype; KIE and OpenRouter expose generic image editing but no documented hidden-image-watermark remover.
- Sources were checked on 2026-07-13 against Google Gemini/SynthID, C2PA 2.4, W3C PNG, IPTC 2025.1, Pillow, Adobe Content Credentials, c2patool, `remove-ai-watermarks`, KIE, and OpenRouter documentation.

## Phase 19 - Metadata And Provenance Cleanup

## Task 24 - Read-Only Metadata Inspector Foundation

Status: Done

Goal:
Inspect ordinary PNG/JPEG metadata without modifying the source file.

Steps:
- Add a focused inspector module outside `main.py`.
- Detect PNG/JPEG by file content and reject unsupported or animated inputs clearly.
- Return structured presence/size summaries for EXIF, XMP, IPTC, comments/text, thumbnails, ICC, DPI, and known generator fields.
- Never emit full metadata values to normal logs.
- Add synthetic PNG, transparent PNG, JPEG, and unsupported-format fixtures.

Acceptance:
- [x] The source hash, size, and modification timestamp remain unchanged after inspection.
- [x] Present, absent, and unsupported categories are reported deterministically.
- [x] Results are serializable and usable by tests, logs, and future UI.

Verification:
- [x] `python -m unittest tests.test_metadata_inspector -v`

Notes:
- Prefer Pillow and standard-library parsing already available in the project.
- Implemented in `metadata_inspector.py` without changing `main.py`; 5 focused tests and all 29 tests pass.
- Review hardened decompression-bomb handling and confirmed that returned/loggable data contains only category counts, sizes, and allowlisted field names.

## Task 25 - Bounded C2PA Presence Inspector

Status: Done

Goal:
Detect embedded C2PA structures locally without validating signatures or using the network.

Steps:
- Detect PNG `caBX` and JPEG APP11/JUMBF structures with strict length bounds.
- Return `present`, `not present`, or `not validated` separately from ordinary metadata.
- Add malformed, truncated, and oversized-segment fixtures.
- Integrate the result into the Task 24 inspector schema.

Acceptance:
- [x] Detection never claims a manifest is valid.
- [x] Corrupt inputs fail safely without unbounded reads or memory allocation.
- [x] No remote manifest is fetched automatically.

Verification:
- [x] `python -m unittest tests.test_c2pa_inspector -v`

Notes:
- Do not add `c2pa-python` until its packaging and build impact are explicitly justified.
- Implemented as a standard-library bounded scan in `metadata_inspector.py`; schema v2 keeps C2PA presence and `not_validated` separate from ordinary metadata categories.
- Review added exact JPEG JUMBF/description `LBox`, extended-`LBox`, contiguous APP11 `En/Z`, description-toggle, overrun, and sequence-gap checks instead of treating marker presence as a complete container.
- Eight focused tests and all 37 project tests pass; 54 embedded fixtures from the official `contentauth/c2pa-rs` checkout were detected with no non-OK present result.

## Task 26 - Selective Metadata Cleanup Core

Status: Done

Goal:
Remove selected ordinary and AI/service metadata while preserving selected export data and image pixels.

Steps:
- Add a cleanup module with independent EXIF, XMP, IPTC, comments/text, thumbnail, and known-generator options.
- Use a documented allowlist for AI/service fields instead of deleting unknown fields by guess.
- Preserve ICC and DPI independently when selected.
- Write to a temporary PNG, validate it, then atomically publish the new output.
- Compare decoded pixels, dimensions, and alpha before and after metadata-only cleanup.

Acceptance:
- [x] Checked categories are removed and unchecked categories remain where the output format supports them.
- [x] ICC and 300 DPI are preserved when selected.
- [x] Pixel values, dimensions, and alpha are unchanged.
- [x] A failure leaves the source and previous output intact.

Verification:
- [x] `python -m unittest tests.test_metadata_cleanup -v`

Notes:
- This task contains no C2PA or visible/pixel watermark handling.
- Implemented a shared exact-match allowlist in `metadata_policy.py`: EXIF `Software`; normalized exact PNG/JPEG text names for software, prompt, model, digital-source, and generator identifiers; and exact XMP `CreatorTool`/`DigitalSourceType` properties. Unknown fields and EXIF camera `Model` are not guessed.
- C2PA-bearing or indeterminate inputs are rejected until Task 27 can make removal explicit; multiple JPEG comments and duplicate PNG text keys are rejected unless their selected category is removed.
- Added bounded file/pixel/dimension/metadata preflight, stripe-based pixel/alpha hashing, EXIF overlap validation, value-safe metadata digests, and atomic same-directory publication.
- Fifteen focused cleanup tests and all 52 project tests pass; three review passes closed C2PA, transparency, EXIF overlap, UTF-16 XMP, allowlist consistency, metadata preservation, JPEG comment, and memory-bound findings.

## Task 27 - C2PA Export Cleanup

Status: Done

Goal:
Remove supported embedded C2PA data or references from the new PNG export when explicitly selected.

Steps:
- Add owned PNG/JPEG fixtures containing embedded-manifest and remote-reference structures.
- Ensure the new PNG does not carry selected embedded C2PA structures or selected external-manifest references.
- Re-run the inspector after export and distinguish removed file structures from remote records and soft bindings.
- Abort publication if post-save validation does not match the selected action.

Acceptance:
- [x] Embedded structures selected for cleanup are absent from the new PNG.
- [x] The source file remains unchanged.
- [x] Logs never claim that remote manifests or pixel soft bindings were deleted.

Verification:
- [x] `python -m unittest tests.test_c2pa_cleanup -v`

Notes:
- This task validates the limited `REMOVE` claim in `CLEANUP_CAPABILITY_MATRIX.md`.
- Added explicit `remove_embedded_c2pa` cleanup for bounded PNG `caBX`, JPEG APP11/JUMBF, valid XMP `self#jumbf=c2pa/...`, and supported HTTP(S) `.c2pa`/JUMBF references in the new PNG only.
- Inspector schema v3 separates embedded containers, embedded XMP pointers, supported external references, and unclassified provenance values; no remote fetch or signature validation is performed.
- Unknown or mixed provenance values abort selective cleanup unless the whole XMP category is explicitly removed. Duplicate PNG XMP keys abort before any `dict` conversion.
- Selective XMP filtering preserves packet wrappers, comments, processing instructions, and unrelated XMP fields; a bounded raw PNG text scan includes metadata placed after `IDAT`.
- Sidecar files, remote manifests, and pixel soft bindings are never touched. Eleven focused C2PA cleanup tests and all 63 project tests pass after three review passes.

## Task 28 - Metadata Cleanup UI And Settings

Status: Done

Goal:
Expose independent metadata/C2PA cleanup choices without changing current defaults.

Steps:
- Add a compact `Очистка файла` section near final export.
- Add independent controls for supported metadata categories and embedded C2PA.
- Add `Сохранить ICC-профиль` and `Сохранить DPI` choices to the right of the related action.
- Save and restore settings; cleanup remains disabled for legacy configs while preservation options default to enabled.

Acceptance:
- [x] Every supported category can be enabled independently.
- [x] Old config files preserve current processing behavior.
- [x] Controls do not overlap at the supported offscreen viewport.

Verification:
- [x] `$env:QT_QPA_PLATFORM='offscreen'; python -m unittest tests.test_cleanup_ui -v`

Notes:
- Do not rearrange unrelated controls.
- Added seven independent removal choices plus ICC/DPI preservation choices. Cleanup remains disabled for legacy configs, ICC/DPI preservation defaults to enabled, and all 65 project tests pass.

## Task 29 - Shared Final-Save Cleanup Integration

Status: Done

Goal:
Run selected metadata cleanup once through the shared final-save path.

Steps:
- Integrate inspection and cleanup after trim and before final completion is reported.
- Use the same path for generate-only, generate-and-process, process-only, local, and mixed runs.
- Keep `raw/` intermediates unchanged for diagnostics.
- Log found, removed, preserved, unsupported, and failed categories without metadata values or secrets.

Acceptance:
- [x] Disabled cleanup is behaviorally equivalent to the current application.
- [x] Every final workflow uses the same cleanup decision and validation path.
- [x] A cleanup failure does not publish a corrupt or partial output.

Verification:
- [x] `python -m unittest tests.test_final_save_cleanup -v`
- [x] `python -m unittest discover -s tests -v`

Notes:
- This is the first user-complete cleanup slice.
- All final workflows now publish through one same-directory staging path. Cleanup-only process runs need no KIE key, trim precedes cleanup, raw intermediates stay unchanged, C2PA cannot be hidden by trim/DPI conversion, and cleanup failures leave prior outputs untouched.
- Ten focused final-save tests and all 75 project tests pass after three review passes.

## Task 30 - Metadata Cleanup Acceptance And Documentation

Status: Done

Goal:
Close the metadata/C2PA slice before starting pixel-changing watermark work.

Steps:
- Review PRD, capability matrix, task results, changelog, and author instructions.
- Verify every cleanup checkbox separately and in one combined local pipeline.
- Record exact supported formats, preservation behavior, and unsupported claims.
- Fix only blocking issues discovered by this review.

Acceptance:
- [x] Documentation matches tested behavior.
- [x] Metadata cleanup never changes visible pixels or alpha.
- [x] Existing processing remains usable with cleanup disabled.

Verification:
- [x] `python -m py_compile .\main.py`
- [x] `python -m unittest discover -s tests -v`

Notes:
- Do not start visible-mark work until this gate passes.
- Every removal choice passes an independent PNG/JPEG fixture, and one combined local pipeline verifies one cleanup call plus identical decoded pixels/alpha before and after metadata cleanup.
- `CLEANUP_CAPABILITY_MATRIX.md` now records implemented formats, bounds, preservation behavior, C2PA scope, unsupported claims, and the 300 DPI precedence rule. Two focused acceptance tests and all 77 project tests pass.

## Phase 20 - Visible Generator Marks

## Task 31 - Local Visible-Mark Detector Prototype

Status: Done - prototype evidence completed; production scope decided in Task 34

Goal:
Measure whether `lana-info/remove-ai-watermarks` reliably localizes supported visible generator marks.

Steps:
- Pin and record the evaluated repository commit and Apache-2.0 attribution requirements.
- Run detection outside the application on owned marked and unmarked fixtures.
- Save only masks, confidence, location, and timing results; do not change production code.
- Measure false positives across clipart, photos, illustrations, and textured corners.

Acceptance:
- [x] Gemini and Doubao detection rates are documented for the available reproducible marked fixtures.
- [x] False positives are measured on five unmarked image fixtures.
- [x] No heavy dependency is added to the main application.

Verification:
- [x] Prototype command and results are recorded in `VISIBLE_MARK_DETECTOR_EVAL.md`.

Notes:
- Detection approval does not approve an inpainting backend.
- Jimeng/Samsung remain an explicit evidence gap. The user-owned Gemini marked and
  unmarked fixture gate was completed in Task 32; Task 34 limits automatic
  integration to Gemini.

## Task 32 - Local Visible-Mark Inpainting Benchmark

Status: Done - cv2 established as the bounded baseline; superseded by Task 37 quality acceptance

Goal:
Choose a local fill method for confirmed masks without unacceptable damage outside the marked region.

Steps:
- Compare cv2, MI-GAN, and LaMa where available using the same masks.
- Compare automatic masks with a user-confirmed rectangular/mask fallback.
- Measure changed pixels outside the requested mask and inspect texture continuity.
- Record runtime, RAM, model downloads, and supported image classes.

Acceptance:
- [x] Provisional local default/fallback selected: cv2 with automatic or user-confirmed mask.
- [x] The bounded benchmark changed zero pixels outside the supplied mask.
- [x] Benchmark never overwrites originals; backend failures are reported without publishing output.

Verification:
- [x] Before/after/mask comparisons are inspected on owned fixtures; decoded pixels and alpha were verified.

Notes:
- Keep benchmark assets outside git unless small and redistributable.
- MI-GAN/LaMa were unavailable during this bounded baseline. Task 37 later evaluated and bundled the official MIT MI-GAN ONNX model after the `cv2` production result failed the 200% visual quality gate; LaMa remains unselected.

## Task 33 - KIE Mask-Edit Benchmark

Status: Done - KIE rejected for precise visible-mark cleanup

Goal:
Determine whether KIE 4o mask editing is a better fallback for visible marks than local inpainting.

Steps:
- Use the smallest useful paid sample set with the existing KIE key.
- Send explicit masks and prompts; preserve original aspect ratio and request PNG.
- Compare changes inside and outside the mask, output metadata, cost, and latency.
- Record provider errors and invalid-output handling.

Acceptance:
- [x] KIE is compared against the selected local method on identical fixtures.
- [x] Cost and visible changes outside the mask are recorded.
- [x] No KIE key appears in logs or saved artifacts.

Verification:
- [x] Manual comparison and request-cost evidence are recorded.

Notes:
- This task spends credits and must remain a minimal benchmark.
- API ratio constraints and the safe paid-test protocol are recorded in `TASK33_KIE_MASK_BENCHMARK.md`.
- Two native 4o mask payloads were rejected before generation; one GPT Image 1.5
  mask-reference task succeeded at a listed `$0.02` and took `102.485` seconds.
- The KIE output changed `78.3491%` of content pixels outside the mask versus `0%`
  for local `cv2`, so no additional request from the authorized five was justified.

## Task 34 - Visible-Mark Provider Decision Gate

Status: Done - local-only go decision with Gemini-only automation

Goal:
Choose local, KIE, user-confirmed-only, or no automatic visible-mark removal.

Steps:
- Compare Tasks 31-33 against one quality rubric.
- Select supported marks, image classes, default provider, and fallback.
- Update the capability matrix and mark Tasks 35-37 active or skipped.

Acceptance:
- [x] The decision is based on saved evidence rather than a single image.
- [x] Automatic processing is rejected for any class with unsafe false positives.
- [x] User-confirmed mask fallback remains available when automatic detection is not approved.

Verification:
- [x] Decision and rationale are recorded in PRD/project documentation and changelog.

Notes:
- No production integration belongs to this gate.
- Automatic local detection/removal is approved only for the small Gemini corner
  mark on owned/licensed PNG/JPEG. Doubao and unmeasured/unknown small service marks
  require a user-confirmed bounded mask; unsupported images remain unchanged.
- At this gate, local `cv2` was the only evaluated precise provider. Task 37 later
  retained the same local-only UI and bounded-mask rules but replaced `cv2` after
  production visual acceptance with reverse-alpha Gemini recovery and bundled MI-GAN.
  KIE and LaMa are not selectable. The feature remains disabled by default.

## Task 35 - Visible-Mark UI And Settings

Status: Done - local-only controls added with legacy-safe defaults

Goal:
Expose only the approved visible-mark controls.

Steps:
- Add an independent visible-mark checkbox with `Gemini automatically` and
  `User-confirmed area` modes; do not add a KIE/provider selector.
- Place parameters to the right of the action and keep the step disabled by default.
- Save/load settings without affecting legacy configs.
- Show when user confirmation is required.

Acceptance:
- [x] Controls match the Task 34 decision exactly.
- [x] Existing UI remains unchanged while the feature is disabled.
- [x] Unsupported automatic modes are not selectable.

Verification:
- [x] `$env:QT_QPA_PLATFORM='offscreen'; python -m unittest tests.test_visible_mark_ui -v`

Notes:
- Automatic modes for Doubao, Jimeng, Samsung, and unknown marks are intentionally unavailable.
- Added one disabled-by-default row before upscale with only `Gemini automatically`
  and `User-confirmed area`. The confirmation status appears only for the second
  mode; no KIE/provider control was added.
- Task 35 introduced config/UI only; Worker integration was completed separately in Task 36.

## Task 36 - Visible-Mark Pipeline Integration

Status: Done - local-only step integrated before the first upscale

Goal:
Run approved visible-mark cleanup before upscale without changing unrelated processing.

Steps:
- Insert the step before the first upscale pass.
- Save the result into `raw/` and validate dimensions, mode, and non-empty pixels.
- Leave unmarked images unchanged when no mark is confidently found.
- Handle cancellation, provider failure, and user-confirmation requirements safely.

Acceptance:
- [x] The step runs only when enabled.
- [x] Existing processing order after the step remains unchanged.
- [x] Failed cleanup does not overwrite the source or previous final output.

Verification:
- [x] `$env:QT_QPA_PLATFORM='offscreen'; python -m unittest tests.test_visible_mark_pipeline -v`
- [x] `$env:QT_QPA_PLATFORM='offscreen'; python -m unittest discover -s tests -v`

Notes:
- Metadata cleanup still runs only at final save.
- Visible-mark cleanup is local-only and must never require or call KIE.
- Vendored only the pinned Apache-2.0 Gemini detector and two required templates
  from `remove-ai-watermarks` commit `190dc89d234fd7e3a61ff755f01251c9c0b87ef0`;
  no upstream model weights or removal engines were added.
- Automatic Gemini removal requires confidence `>= 0.5`; a lower score leaves the
  source unchanged and creates no visible-mark `raw/` file.
- User-confirmed mode opens a local rectangle selector for each process-only file,
  limits the area to 15% of the image, and keeps coordinates only in current-run memory.
- Successful output is validated and atomically saved as
  `raw/*_visible_mark_*.png`; source pixels and prior outputs remain intact on failure
  or cancellation.
- Tracked Windows/macOS PyInstaller commands include the two templates, Apache
  license, and attribution notice; no application build or release was run.
- Six focused tests and all 85 project tests pass. A real owned Gemini fixture scored
  `0.694789`, changed `0` pixels outside the mask, and preserved the source hash; an
  unmarked screenshot scored `0.184643` and produced no raw output. No API request was made.
- Task 37 subsequently replaced the initial `cv2.inpaint` fill after its 200% visual
  acceptance exposed rectangular patches; the step order, UI modes, and local-only
  routing remain unchanged.

## Task 37 - Visible-Mark Acceptance

Status: Done - local-only quality acceptance passed

Goal:
Verify the complete visible-mark slice on marked and unmarked general images.

Steps:
- Test automatic Gemini and user-confirmed flows on approved general-image fixtures.
- Verify local-only routing and that visible-mark cleanup never requires a KIE key.
- Compare results at normal view and 200% zoom.
- Update supported/unsupported documentation.

Acceptance:
- [x] Approved fixtures meet the recorded quality rubric.
- [x] Unmarked fixtures remain unchanged.
- [x] Logs and UI describe detection and removal accurately.

Verification:
- [x] `$env:QT_QPA_PLATFORM='offscreen'; python -m unittest tests.test_visible_mark_pipeline -v`
- [x] `$env:QT_QPA_PLATFORM='offscreen'; python -m unittest discover -s tests -v`
- [x] Manual comparison is recorded in `CHANGELOG.md`.

Notes:
- Acceptance included two marked Gemini fixtures, one user-confirmed Doubao fixture,
  five clean upstream fixtures, and one clean user-owned clipart fixture.
- Reverse-alpha Gemini recovery and bounded local MI-GAN passed normal-size and 200%
  visual inspection. All three marked files changed `0` pixels outside the mask;
  all six unmarked files remained unchanged and produced no visible-mark output.
- Source hashes, dimensions, modes, and alpha were preserved. The run made `0`
  KIE/API requests. Evidence is stored outside git in
  `C:\Users\belou\Downloads\output\task37-visible-mark-acceptance-fixed`.
- The pinned MI-GAN model, MIT license, notice, and Windows/macOS packaging entries
  are tracked. No application build, release, tag, or workflow run was performed.
- Eight focused visible-mark tests and all 87 project tests pass.

## Phase 21 - Hidden Pixel Markers: Managed API First

## Task 38 - Pixel-Watermark Status Contract

Status: Done - provider-neutral claim-safe contract added

Goal:
Represent hidden-marker evidence without turning metadata proxies into false removal claims.

Steps:
- Define structured statuses: `detected`, `not detected`, `not verified`, and `unsupported`.
- Keep metadata/C2PA hints separate from pixel-level detector evidence.
- Define the manual or official verification handoff for SynthID.
- Add safe log formatting and tests.

Acceptance:
- [x] `not detected` never means proven human-made.
- [x] Processing success is separate from detector result.
- [x] Unknown markers never receive a false `removed` result.

Verification:
- [x] `python -m unittest tests.test_watermark_status -v`

Notes:
- This contract is shared by KIE, OpenRouter, and any GPU worker.
- `watermark_status.py` returns separate `processing`, `pixel_evidence`,
  `file_hints`, and `verification_handoff` branches. Metadata/C2PA hints cannot
  change pixel evidence, detector evidence identifies the checked input/output
  stage, and the schema has no `removed` status.
- Unverified SynthID uses the official Gemini handoff; unknown markers use manual
  or external verification. The formatter emits only allowlisted labels and never
  echoes provider/user values.
- Six focused tests and all 93 project tests pass. Task 38 adds no UI, API call,
  or pipeline behavior.

## Task 39 - KIE Whole-Image Regeneration Prototype

Status: Done

Goal:
Test whether the existing KIE integration is sufficient for whole-image regeneration before adding infrastructure.

Steps:
- Test GPT Image 2 image-to-image first and FLUX image-to-image as fallback.
- Do not use Google/Nano Banana models for SynthID removal because their outputs receive SynthID.
- Use owned photos, illustrations, text-heavy images, faces, and clipart.
- Record quality, dimensions, alpha behavior, latency, credits, and metadata/provenance added to outputs.
- Re-check a known SynthID sample through the available official verification flow.

Acceptance:
- [x] KIE results are evaluated on all required image classes.
- [x] Cost and quality are recorded per model/resolution.
- [x] Results report `not verified` unless detector evidence exists.

Verification:
- [x] Minimal paid benchmark results are recorded outside production code.

Notes:
- `TASK39_KIE_REGENERATION_BENCHMARK.md` records one GPT Image 2 and one FLUX 2
  Pro `1K` generation. GPT returned `1254x1254` RGB and FLUX returned
  `1024x1024` RGB; both lost alpha and added embedded C2PA. GPT preserved the
  fixture better, while FLUX spread the fine grid across the board and changed
  layout/text.
- The known Gemini-origin fixture and both outputs remain `not_verified` because
  no authenticated official Gemini detector session was available. Processing
  success is not reported as watermark removal.
- The five-attempt authorization is exhausted: Task 33 used three attempts and
  Task 39 used two. The reusable harness now blocks live generation globally,
  independent of output directory; the recorded model snapshots total
  `11 credits / $0.055` without claiming actual billing.
- KIE does not pass the universal quality gate, so Task 40 is activated. No
  production UI or pipeline behavior was changed.
- Five focused benchmark tests and all 98 project tests pass. They cover the
  closed global budget, credit snapshots, real alpha, safe status claims, and the
  enabled FLUX safety checker.

## Task 40 - OpenRouter Managed-API Fallback Prototype

Status: Done

Goal:
Test one current OpenRouter image-to-image candidate only if KIE is insufficient.

Steps:
- Re-check current image-model capabilities, pricing, and provider watermark policy.
- Select one non-Google candidate and run the same fixtures/rubric as Task 39.
- Record output metadata, cost, latency, quality, and detector status.
- Keep the prototype outside the main application.

Acceptance:
- [x] OpenRouter is compared directly with the failed or partial KIE cases.
- [x] No OpenRouter key appears in logs or fixtures.
- [x] The result does not receive production approval without detector and quality evidence.

Verification:
- [x] Preparation command and pending comparison table are recorded.
- [x] One live result and the completed comparison table are recorded.

Notes:
- `recraft/recraft-v4.1-utility` was selected from the current dedicated Image
  API records as the single non-Google candidate. Its endpoint snapshot is
  `$0.035` per output image and accepts one reference image.
- The provider has no documented hidden pixel-watermark removal guarantee or
  checked pixel-watermark policy. The result must remain `not_verified` without
  detector evidence.
- `scripts/run_openrouter_regeneration_benchmark.py` reuses the Task 39 fixture,
  prompt, metrics, metadata/C2PA inspection, and Task 38 status contract. It is
  outside the application and does not change `main.py` or the UI.
- One separately authorized request completed in `12.588 s`; the API response
  reported `$0.035`. Recraft returned `1024x1024` RGB WebP, lost alpha, changed
  `99.9579%` of RGB pixels beyond tolerance, and scored global SSIM `0.177527`.
- Manual review failed: photo subject, face identity, clipart, exact text, and
  fine-grid content were changed. The raw WebP also contains a signed `CRFT`
  provenance chunk. SynthID remains `not_verified`; removal is not claimed.
- Live generation is globally closed again at zero authorized attempts, while
  the local state records the authorized attempt as `1/1` used. The key does not
  appear in the report, fixtures, diff, or git history.
- Ten focused tests cover the real-alpha fixture, closed network gate, global
  one-shot reservation, missing-key behavior, validated response allowlisting,
  signed WebP evidence without provider values, and safe `not_verified`
  analysis, including malformed WebP padding, pre-read size rejection, and RIFF
  boundary enforcement; all 108 project tests pass.
- Three review passes found and fixed bounded-read, test-count, and RIFF-boundary
  issues. No blocking or important finding remains open.
- Decision: OpenRouter/Recraft is not approved for production. Task 41 is active.

## Task 41 - Managed-API Decision Gate

Status: Done - managed APIs rejected; isolated local/GPU feasibility path activated

Goal:
Decide whether KIE alone, KIE plus OpenRouter, or a custom GPU path is justified.

Steps:
- Compare quality, detector evidence, cost, latency, alpha/dimension behavior, and operational complexity.
- Record the user-approved quality threshold and acceptable per-image cost.
- Select a managed provider or explicitly activate Tasks 42-47.
- Update PRD, capability matrix, and later task statuses.

Acceptance:
- [x] No managed API was chosen because none met the complete quality and detector gate.
- [x] KIE was proven insufficient before the conditional local/GPU path was activated.
- [x] The decision names supported image classes and known failure modes.

Verification:
- [x] Decision evidence and activated/skipped tasks are recorded in `TASKS.md` and `CHANGELOG.md`.

Notes:
- This is the required cost-control gate.
- User-approved total OpenRouter test ceiling: `$0.300`; Task 40 consumed
  `$0.035`, leaving at most `$0.265` for Task 41.
- FLUX.2 Max was removed before paid execution because its per-megapixel
  endpoint did not expose a bounded output size.
- The first Seedream request failed with HTTP 400 and was not billed. The RGB
  defaults attempt cost `$0.040`, returned `2048x2048` RGB JPEG, changed the
  face/photo style, lost alpha, added C2PA, and remained `not_verified`.
- Riverflow produced the best visual fidelity and preserved exact text, but it
  lost alpha and remained `not_verified`. Its response reported `$0.264885`
  against the immediately preceding `$0.130` endpoint snapshot.
- Successful Task 41 responses total `$0.304885`; including Task 40, known
  response-reported spend is `$0.339885`. Testing stopped immediately and the
  final live authorization list is empty.
- No managed API is added to production. Task 42 is activated. Exact evidence,
  artifacts, safety controls, and commands are in
  `TASK41_MANAGED_API_DECISION.md`.
- The final state passes 28 focused Task 41 tests and all 136 project tests.

## Phase 22 - Conditional GPU Fallback

## Task 42 - Local remove-ai-watermarks Feasibility

Status: Done - clear local production hardware no-go documented without model downloads

Goal:
Measure the local repository's diffusion pipelines without affecting the application environment.

Steps:
- Pin the evaluated commit and create an isolated Python environment.
- Audit code and downloaded model-weight licenses before execution.
- Compare ControlNet, SDXL, and Qwen where current hardware permits.
- Record model downloads, runtime, VRAM/RAM, quality, dimensions, alpha, and detector result.

Acceptance:
- [x] The main application environment and requirements remain unchanged.
- [x] At least one feasible pipeline or a clear hardware no-go is documented.
- [x] Apache-2.0 and model-weight obligations are recorded.

Verification:
- [x] Exact isolated install/run commands and benchmark results are recorded.

Notes:
- CPU-only execution may be measured but is not a production deployment candidate.
- Evaluated upstream commit `190dc89d234fd7e3a61ff755f01251c9c0b87ef0`
  in `D:\WorkOS\Clipart Generator-task42\.venv-locked` via `uv sync --locked`;
  the application environment,
  `requirements.txt`, `requirements-dev.txt`, `main.py`, and UI were unchanged.
- The machine has `17.95 GiB` physical RAM, an AMD integrated adapter reporting
  `2 GiB`, and no CUDA/XPU/MPS device. The upstream accepts only
  `cpu`/`cuda`/`xpu`/`mps`; AMD DirectML is not supported.
- The CPU path selects FP32. Audited selected weights are `12.92 GiB` for SDXL,
  `15.25 GiB` for SDXL + ControlNet, and `53.74 GiB` serialized BF16 for Qwen.
  Model-weight downloads and inference were therefore stopped at preflight.
- No output exists, so runtime/VRAM/quality/dimensions/alpha are explicitly not
  measured and detector evidence remains `not_verified`. Details and exact
  commands are in `TASK42_LOCAL_WATERMARK_FEASIBILITY.md`.
- Upstream model IDs are not loaded with pinned `revision=` values. The report
  pins the audited snapshots, and the final preflight verified their SHA,
  card-license metadata, and selected file sizes through the official Hugging
  Face metadata API. Any future worker must enforce those revisions and must
  remain isolated from the desktop environment.
- The ControlNet component is Apache-2.0 but its combined pipeline retains
  SDXL Open RAIL++-M obligations. The MIT-marked FP16 VAE is derived from
  SDXL-VAE, so inherited terms require review before any future distribution.
- Upstream supports a slow CPU route, but Task 42 excludes CPU-only production;
  plain-SDXL CPU impossibility is not claimed because inference was not run.
- Verification passed: 13 focused Task 42 tests, 26 pinned-upstream focused
  tests, all 149 application tests, Python compilation, and offscreen
  `SMOKE_OK`. No release/build/workflow was run.

## Task 43 - GPU Serverless Provider Spike

Status: Skipped - Task 42 produced no approved feasible pipeline

Goal:
Choose a scale-to-zero GPU host for the approved local pipeline.

Steps:
- Compare RunPod Serverless first and Modal as fallback using current official pricing and limits.
- Measure cold start, model caching/storage, execution time, timeout limits, and per-image cost.
- Keep active workers at zero during the spike.
- Select one provider and document the rollback/stop procedure.

Acceptance:
- [ ] No always-on GPU cost is created.
- [ ] One provider is selected with an estimated cost range and hard spending limit.
- [ ] The ordinary VPS is excluded from diffusion inference.

Verification:
- [ ] One minimal GPU job completes and billing evidence is recorded.

Notes:
- Stop and remove unused workers/resources after the spike.
- No GPU resource, account, payment, worker, or live job was created.

## Task 44 - GPU Worker Endpoint

Status: Skipped - Task 43 prerequisite was not activated

Goal:
Expose the approved regeneration pipeline through a minimal asynchronous GPU API.

Steps:
- Build a pinned worker image with model cache and `/health` behavior.
- Accept a bounded image input, create a job, and return structured status/output.
- Validate dimensions, file type, output size, non-empty pixels, and timeout/cancellation.
- Delete temporary input/output after the documented retention window.

Acceptance:
- [ ] The worker scales from zero and processes one owned fixture successfully.
- [ ] Invalid or oversized inputs are rejected before GPU work.
- [ ] Failed jobs return actionable errors and no partial output.

Verification:
- [ ] Worker unit tests and one live serverless smoke pass.

Notes:
- Keep the worker separate from the desktop repository unless Task 43 selects a documented subdirectory contract.

## Task 45 - Ordinary VPS Gateway And Secret Boundary

Status: Skipped - no distributed GPU service was approved

Goal:
Use the existing ordinary VPS only to protect GPU credentials, authorize clients, and coordinate jobs.

Steps:
- Define whether the service is personal direct-access or distributed through the license server.
- For distributed access, keep the GPU key on the VPS and authenticate the desktop request.
- Add rate limits, job ownership, maximum sizes, timeouts, retention, and secret-safe logs.
- Prefer temporary/signed transfer rather than permanent image hosting.

Acceptance:
- [ ] No GPU provider secret ships in the desktop application.
- [ ] One user cannot read another user's job or output.
- [ ] Expired files and job records follow the documented retention policy.

Verification:
- [ ] Gateway authorization, limit, expiry, and error tests pass.

Notes:
- Mark `Skipped` for a strictly personal endpoint where the user supplies their own key locally.

## Task 46 - GPU Service Desktop Adapter

Status: Skipped - no GPU endpoint or gateway was approved

Goal:
Add a tested desktop client for the selected GPU endpoint without exposing infrastructure details to the pipeline.

Steps:
- Add a narrow provider adapter for submit, status, cancel, and download.
- Route through the VPS gateway when Task 45 requires it.
- Validate downloaded output before handing it to the pipeline.
- Add network-free tests for success, timeout, cancellation, invalid output, and secret-safe errors.

Acceptance:
- [ ] The adapter is independent from KIE and OpenRouter code.
- [ ] No endpoint secret appears in logs.
- [ ] Failed downloads never replace a valid prior file.

Verification:
- [ ] `python -m unittest tests.test_gpu_watermark_provider -v`

Notes:
- Do not add UI controls in this task.

## Task 47 - GPU Cost And Reliability Acceptance

Status: Skipped - no custom GPU path reached acceptance

Goal:
Confirm that the custom GPU path is worth maintaining before exposing it to users.

Steps:
- Run a bounded batch across approved image classes.
- Measure cold/warm latency, failures, retries, cancellation, and actual per-image cost.
- Verify worker scale-down and temporary-file cleanup.
- Compare quality and cost against the best managed API result.

Acceptance:
- [ ] The custom path beats or materially complements the managed API decision.
- [ ] Cost limits and failure behavior are acceptable.
- [ ] Otherwise Tasks 48-49 use only the managed API path.

Verification:
- [ ] Benchmark, billing, and cleanup evidence are recorded.

Notes:
- Shut down and delete unused GPU resources after acceptance.

## Phase 23 - Pixel Regeneration Integration And Closeout

## Task 48 - Pixel-Regeneration UI And Settings

Status: Skipped - both managed and custom regeneration paths are no-go

Goal:
Expose the approved whole-image regeneration path as a separate optional action.

Steps:
- Add `Экспериментальная перегенерация` with only approved providers and parameters.
- Explain before execution that the entire image may change.
- Keep the option disabled by default and independent from background removal and metadata cleanup.
- Save/load settings and apply existing masked-key rules for user-supplied API keys.

Acceptance:
- [ ] Unsupported or rejected providers are not selectable.
- [ ] Legacy configs preserve current behavior.
- [ ] The warning appears before a paid or pixel-changing request.

Verification:
- [ ] `$env:QT_QPA_PLATFORM='offscreen'; python -m unittest tests.test_pixel_regeneration_ui -v`

Notes:
- Use the existing vertical processing-order layout.

## Task 49 - Pixel-Regeneration Pipeline And Reinspection

Status: Skipped - no approved regeneration provider exists

Goal:
Run whole-image regeneration safely and report the actual post-processing marker status.

Steps:
- Run regeneration before upscale/background removal unless the accepted provider evidence requires a narrower rule.
- Save the provider output into `raw/` and validate it before continuing.
- Apply the approved transparent-input rule from the prototype.
- Re-run metadata/provenance inspection after regeneration and again after final metadata cleanup.
- Report `detected`, `not detected`, `not verified`, or `unsupported`; never infer removal from request success.

Acceptance:
- [ ] Disabled regeneration leaves the current pipeline unchanged.
- [ ] Provider failure, cancellation, timeout, or invalid output preserves previous files.
- [ ] Final logs separate processing success from detector evidence.

Verification:
- [ ] `python -m unittest tests.test_pixel_watermark_regeneration -v`
- [ ] `python -m unittest discover -s tests -v`

Notes:
- Existing upscale/background/edge/trim order remains unchanged after this optional first step.

## Task 50 - Complete Cleanup Acceptance

Status: Done

Goal:
Verify the complete post-MVP cleanup goal without building or publishing a release.

Steps:
- Review PRD, TASKS, changelog, capability matrix, knowledge base, and author documentation.
- Verify every enabled checkbox independently and in combined local/KIE/approved-provider flows.
- Test old config compatibility, key routing, cancellation, raw/final outputs, and unsupported claims.
- Fix only blocking issues and record later improvements separately.

Acceptance:
- [x] Metadata cleanup preserves pixels/alpha and selected ICC/DPI.
- [x] Visible and hidden mark claims match saved evidence.
- [x] Existing generation and processing remain usable with all cleanup features disabled.
- [x] Conditional GPU tasks are either verified or explicitly marked `Skipped` with rationale.

Verification:
- [x] `python -m py_compile .\main.py .\license_client.py .\tests\test_license_client_security.py .\tests\test_kie_routing.py .\tests\test_main_ui_acceptance.py .\tests\test_photoroom_provider.py .\tests\test_visible_mark_pipeline.py .\tests\test_security_boundaries.py`
- [x] `$env:QT_QPA_PLATFORM='offscreen'; python -m unittest discover -s tests -v` (`176/176` passed)
- [x] Manual comparisons on light/dark backgrounds and multiple image classes are recorded.

Notes:
- Finish with documentation, commit, and push only. Do not build, tag, publish, or create a release.
- The first acceptance pass was reopened after independent review reproduced redirect/header leaks, provider-body logging, final-publication cancellation races, ambiguous upload POST fallback, and insufficient provider-image limits.
- The fixes were covered by regressions and a fresh independent review returned `PASS`, including HTTPS redirect handling and real HTTP 400/422 reference-schema classification.
- The follow-up review added bounded updater responses, HTTPS-only update URL validation, and local-image preflight limits; a second fresh review and a post-refactor fresh review returned `PASS`.
- The current session's bundled Python lacked project runtime dependencies (`PyQt6` and `cv2`), so the new focused runtime tests were syntax-checked but not executed here; the previously recorded 176-test acceptance run remains unchanged.
- Final evidence is recorded in [`TASK50_CLEANUP_ACCEPTANCE.md`](./TASK50_CLEANUP_ACCEPTANCE.md).
- No paid request, model download, build, tag, workflow, or release was run.

## Task 51 - Trustworthy Feature Test Coverage

Status: Done - verified in the project's local `.venv`

Goal:
Cover the application's real user-facing features with deterministic tests that
assert business outcomes and safe failure behavior rather than only code paths.

Scope:
- Image generation: KIE model payloads, reference routing, polling, and result extraction.
- Data validation: supported image boundaries and invalid-input rejection before processing.
- Information preparation: CSV/BOM/delimiter/quotes, prompt normalization, and reference limits.
- Publication boundaries: final-output contracts, license cache lifecycle, and verified updater downloads.

Acceptance:
- [x] A feature matrix is recorded in [`TRUSTWORTHY_TEST_MATRIX.md`](./TRUSTWORTHY_TEST_MATRIX.md).
- [x] Focused generation/preparation/result tests are in `tests/test_trustworthy_feature_contracts.py`.
- [x] A network-free generation integration test verifies request payload, polling,
  download, and publication of one PNG output.
- [x] Positive license lifecycle tests are in `tests/test_license_client_security.py`.
- [x] Positive and negative updater/image-boundary tests are in `tests/test_security_boundaries.py`.
- [x] Negative scenarios cover failed generation, expired license cache, checksum
  mismatch cleanup, corrupt input, and unsupported result shapes.
- [x] Existing final-output, cleanup, UI, provider, and local-processing suites remain part of the required regression set.
- [x] No test performs a paid request, release, publication, commit, or push.

Verification:
- [x] `python -m py_compile .\main.py .\license_client.py .\tests\test_license_client_security.py .\tests\test_security_boundaries.py .\tests\test_trustworthy_feature_contracts.py`
- [x] Bundled runtime: `python -m unittest tests.test_license_client_security -v` (`7/7` passed).
- [x] `git diff --check`.
- [x] `$env:QT_QPA_PLATFORM='offscreen'; .\.venv\Scripts\python.exe -m unittest discover -s tests -v` (`198/198` passed).

Notes:
- The bundled Codex runtime lacked `PyQt6` and `cv2`; the project's local
  `.venv` was created and populated from `requirements.txt` for verification.
- Independent review rated the first pass `5/10`; the follow-up added the
  missing generation integration, public activation/cache flow, checksum
  mismatch cleanup, and corrupt-input regressions. Those import-dependent
  tests still require the project's normal environment.
- No production behavior was changed for this testing task.

## Task 52 - Processing Settings Clarity And Bundled Local Upscaler

Status: Done - verified without build or release

Goal:
Make the processing settings understandable and stable for everyday use while
preserving existing configuration keys and processing behavior.

Scope:
- Group processing controls by operation: upscale before background removal,
  upscale after background removal, background removal, Local rembg, and BEN2.
- Rename visible-watermark and BEN2 controls in user-facing text.
- Add one full metadata cleanup checkbox that removes all supported metadata
  while preserving ICC and DPI; retain old config keys only for migration.
- Treat Real-ESRGAN as an application-bundled resource and add it to the
  existing PyInstaller build recipe; do not run the build in this task.

Acceptance:
- [x] Existing provider data values, config keys, and processing order remain
  compatible with the prior UI.
- [x] BEN2 is described as a local experimental background-mask model, not a
  neural watermark remover.
- [x] Full cleanup preserves ICC/DPI and leaves image pixels/alpha untouched.
- [x] The bundled Real-ESRGAN path is used for source and packaged runs, and
  the build recipe includes its folder.
- [x] No generic hidden neural watermark/SynthID removal claim was added.

Verification:
- [x] `python -m py_compile .\\main.py`
- [x] `$env:QT_QPA_PLATFORM='offscreen'; .\\.venv\\Scripts\\python.exe -m unittest tests.test_cleanup_ui tests.test_main_ui_acceptance tests.test_visible_mark_ui tests.test_local_processing_acceptance -v` (`20/20` passed)
- [x] `git diff --check`

Notes:
- `README.md` is not present in this repository; the review used `README_AUTHOR_SHORT.md`, `PRD.md`, `TASKS.md`, and `CHANGELOG.md`.
- The executable and installer were not rebuilt, released, committed, or pushed.

## Task 53 - Compact Processing And Cleanup UI

Status: Done - verified without build or release

Goal:
Keep the application usable on a normal laptop screen while making cleanup
and processing settings easier to understand.

Scope:
- Replace the visible metadata sub-checkboxes with one full-cleanup checkbox;
  preserve ICC and DPI automatically and keep legacy config keys synchronized.
- Move provider/model processing settings to the `Обработка` tab.
- Add scrollable content to the processing and settings tabs and reduce the
  initial window height.
- Explain in the BEN2 block when local mask refinement runs.
- Keep generation, PhotoRoom, and processing prices beside their own fields.

Acceptance:
- [x] One cleanup checkbox enables all supported metadata/C2PA cleanup and
  always preserves ICC/DPI.
- [x] BEN2 timing is visible: it runs as the selected background-removal step
  after the first upscale and before edge shrink/trim.
- [x] Settings pages can be scrolled instead of forcing a tall main window.
- [x] Price labels are contained in the same row as their corresponding model
  or provider field.
- [x] Existing processing order, provider data values, and API behavior remain
  unchanged.

Verification:
- [x] `python -m py_compile .\\main.py .\\tests\\test_cleanup_ui.py`
- [x] `$env:QT_QPA_PLATFORM='offscreen'; .\\.venv\\Scripts\\python.exe -m unittest tests.test_cleanup_ui tests.test_main_ui_acceptance tests.test_visible_mark_ui tests.test_local_processing_acceptance tests.test_photoroom_provider -v` (`25/25` passed)
- [x] `$env:QT_QPA_PLATFORM='offscreen'; .\\.venv\\Scripts\\python.exe -m unittest discover -s tests -v` (`198/198` passed)
- [x] `git diff --check`

Notes:
- No build, release, commit, or push was performed.

## Task 54 - Align Local Background Settings

Status: Done - verified and pushed

Goal:
Align Local rembg and BEN2 controls with the other processing settings.

Acceptance:
- [x] Fixed-width controls are left-aligned within a shared settings column.
- [x] Local rembg and BEN2 fields start on the same vertical line as the
  upscale/background provider fields.
- [x] Generation, processing, cleanup, and provider behavior is unchanged.

Verification:
- [x] Qt geometry smoke check reports the same `x=377` start for the upper
  provider, Local rembg, and BEN2 controls.
- [x] `$env:QT_QPA_PLATFORM='offscreen'; .\\.venv\\Scripts\\python.exe -m unittest discover -s tests -v` (`198/198` passed)
- [x] `git diff --check`

## Task 55 - Silent Auto-Update to 2.0

Status: Superseded - legacy public update channel is inactive

Goal:
Enable legacy 1.x installs to auto-upgrade to `2.0` during startup without requiring
manual click, using the existing manifest and installer flow.

Scope:
- Keep update manifest parsing and HTTPS validation unchanged.
- Keep checksum validation and download limits in place.
- Add auto-apply behavior when `check_for_updates` is triggered at app startup.
- Download large installers in chunks with bounded retries to avoid partial files.

Acceptance:
- [x] Update manifest check uses `latest_version` from public `version.json` and respects `APP_VERSION` comparison.
- [x] Auto-apply path skips the interactive confirmation on startup update checks.
- [x] Installer download is bounded, streamed, and cleaned up on checksum/failure errors.
- [ ] Historical acceptance not pursued: manual/offline validation of the old
  `1.3` -> `2.0` public-channel flow on real clients.

Notes:
- The private GitHub updates repository is no longer an active delivery channel.
- Do not continue this flow or modify its public Release/manifest without a
  separate migration decision.
- No release/build workflow is started by this task.

## Phase 24 - Shared License And Update Service

Reference: `LICENSE_UPDATE_SERVICE_PRD.md`

### Task 56 - Approve License And Update Service Architecture

Status: Complete

Goal:
Approve the business rules, security boundaries, API surface, database model,
and free VDS-first infrastructure before implementation.

Acceptance:
- [x] One license is limited to one active device.
- [x] Device reset is administrator-only; there is no customer self-service reset.
- [x] The administrator can generate keys in a protected panel.
- [x] Offline use is prohibited and cannot be authorized by a local cache.
- [x] Multiple products and separate update entitlements are represented.
- [x] The first stage requires no new paid service.
- [x] Exact service URL is `https://services.etsyneuroclub.com/licenses`.
- [x] License duration is represented by `expires_at`; perpetual licenses are supported.
- [x] Update entitlement is represented independently by `updates_until`.
- [x] Independent architecture/security review findings are reflected in the PRD.

### Task 57 - Create Separate Private Server Repository

Status: Complete

Scope:
- Create the server repository only after architecture approval.
- The separate private repository exists at
  `/root/projects/Clipart Generator/license-service`, with environment-only
  configuration, migrations, tests, API, administration, and deployment
  documentation. Secrets, database state, and artifacts remain outside Git.
- Add server-specific instructions, secret exclusions, migrations, tests, and
  deployment boundaries.
- Do not copy `licenses.db`, desktop secrets, or release artifacts.

### Task 58 - Implement Core License API And Database

Status: Implemented and deployed

Scope:
- Implement products, high-entropy keys, HMAC lookup and protected key
  verification, one-device activation, per-install asymmetric device proof,
  nonce-based validation, signed responses, administrative release,
  revocation, audit events, and transactional concurrency protection.
- Use isolated PostgreSQL roles and migrations.
- Enforce one active device with a PostgreSQL partial unique index and a
  transaction; enforce unique product/version/channel/platform releases.
- Use separate license/update signing keys with `kid`, rollover, backup,
  rotation, and revocation procedures.
- Use the approved v1 Ed25519/RFC 8785 signed envelope with explicit schema and
  algorithm versions.
- Do not implement offline authorization.

Verification:
- Unit and integration tests for all license states and product isolation.
- Concurrent activation test proves that two devices cannot both activate.
- Signature, secret-redaction, response-bound, rate-limit, and migration tests.

### Task 59 - Implement Protected Administrative Panel

Status: Implemented and deployed

Scope:
- Create the first administrator locally; expose no public registration.
- Administrator login uses the `admin` username and password. TOTP is the
  additional second factor; secure sessions, recovery codes, and rate limiting
  are implemented.
- Generate one or multiple keys and show full values only on creation/export.
- Search, suspend, revoke, extend, and manually reset a device binding.
- Display safe device/license identifiers and an immutable audit history.
- Require recent re-authentication for exports, resets, revocation, release
  publication, and signing-key operations.
- No public customer reset route or UI.

### Task 60 - Prepare Free Staging Deployment On VDS

Status: Deployed; recurring operations remain

Scope:
- Configure the approved subdomain, free TLS, reverse proxy, isolated service,
  isolated PostgreSQL database, private artifact directory, health checks,
  logging, rate limits, and backup/restore procedure.
- Select an existing no-new-cost off-VDS backup target controlled by the owner;
  complete a restore test before production.
- Do not alter existing VDS projects or reuse their database credentials.
- Do not start production service or publish releases in this task.

Verification:
- [x] DNS, TLS, reverse proxy, isolated PostgreSQL, health checks and service deployment completed.
- [x] Backup and rollback image were prepared before deployment.
- [x] First restore drill completed successfully on 2026-08-14.
- [ ] Continue periodic backup/restore and monitoring checks as operations work.

### Task 61 - Integrate Mandatory Online License Gate

Status: Planned - separate desktop task

Branch: `codex/license-server`

Scope:
- Replace the prototype client contract with the approved signed API.
- Generate a per-install Ed25519 device key and protect its serialized private
  key for the current Windows user with DPAPI; use challenge/response proof and
  fresh nonces without claiming hardware-backed non-exportability.
- Require a fresh server round-trip at startup and immediately before every
  protected operation; periodic checks are additional only.
- Preserve completed outputs and avoid destructive shutdown.
- Remove prototype authorization: the three-day/offline cache and
  `use_offline=True`, client/public `/deactivate`, plaintext license-key
  response/storage, repeated license-key validation, and static admin token.

Verification:
- Offline and invalid-license states fail closed without starting providers.
- Disconnect immediately after validation; the next protected operation is
  blocked.
- Every generation, processing, batch, and mixed-workflow entry point is gated.
- No desktop or public route can reset/release a device binding.
- Valid license permits existing generation and processing unchanged.
- Administrator reset invalidates the old device and permits one replacement.
- Windows packaged-client behavior is checked in an isolated environment.

### Task 61A - Mandatory Startup License Gate Hotfix

Status: Windows installer built - manual Windows acceptance pending

Root cause:
- The signed license gate protected worker starts and retries, but the release
  entrypoint opened the main V3 interface before invoking it.

Implemented:
- Require a fresh online validation before the main window can open.
- If no valid saved activation exists, show the license-key dialog immediately.
- Close startup on cancellation, offline validation, server rejection, or a
  missing license gate.
- Revalidate online after a newly entered key is activated.
- Show license status, the fresh online-check time, `Сменить лицензию`, and
  `Настройки API` before a work mode is selected; never display the full key.
- Default new work to `Pictures/Clipart Generator` and persist the last selected
  work and processing-result folders outside the install directory.

Verification:
- [x] `python -m unittest tests.test_release_entrypoint -v`
- [x] Critical license suite: 41 tests passed.
- [x] Current full desktop suite: 420 tests passed, 1 expected skip.
- [x] Source packaged-entrypoint smoke verifies the masked key field and
  fail-closed startup behavior.
- [x] First-screen license/API controls pass offscreen layout and action tests.
- [x] Pictures default and last-folder restoration pass restart regressions.
- [x] Rebuild the Windows installer from implementation commit `43682ac` in run
  `31909510317` (Windows success; macOS skipped).
- [x] Verify the packaged Windows `.exe` passes `--release-entrypoint-smoke`,
  including startup licensing, visible license/API controls, their signal
  connections, and the Pictures-based default.
- [ ] Manually confirm on Windows that the key dialog appears before the main UI.

### Task 62 - Design And Implement Private Update Delivery

Status: Server deployed - Windows build and acceptance pending

Branches: desktop `codex/feature-updates-diagnostics`; server
`codex/feature-secure-updates`

Scope:
- Add product/platform release records, signed manifests bound to the licensed
  device request, short-lived download tokens, local VDS artifact retention,
  and explicit installer confirmation.
- Keep free Ed25519 service/artifact signatures separate from optional Windows
  Authenticode, which is not required by the free first stage.
- Replace the old client channel with one asynchronous licensed V3 check after
  startup. `Не сейчас` downloads nothing and asks again on the next launch.
- Do not modify existing public releases or publish a new build automatically.

Verification:
- [x] License and update entitlement gates are independent and fail closed.
- [x] Manifest delegation/signature, request binding, HTTPS, size, SHA-256,
  token expiry/use bounds, and interrupted-download cleanup are tested.
- [x] The V3 entrypoint no longer invokes the legacy updater.
- [x] Apply server migration 006 after a fresh backup, deploy with a prepared
  rollback image, and verify public health, artifact upload, and signed update
  key delegation.
- [ ] Validate the manifest/download path with a draft revision after the new
  Windows artifact exists.
- [x] Build Windows `3.0.1` in run `31924194111`; verify the packaged V3
  entrypoint, exact internal version, installer creation, and downloaded SHA-256.
- [ ] Windows upgrade, cancellation, UAC, and rollback safety receive manual
  isolated checks after the separately authorized build.

### Task 62A - Add User-Facing Diagnostic Journal

Status: Implementation complete - packaged Windows visual acceptance pending

Implemented:
- Keep at most three launch sessions and 10 MiB total, with bounded events and
  a non-blocking in-memory fallback if application-data storage is unavailable.
- Show `Журнал диагностики` before mode selection and in the shared wizard.
- Record startup, license, update, configuration, project, processing, retry,
  cancellation, and terminal outcomes without keys, prompts, images, raw
  provider responses, environment values, or full personal paths.
- Allow copying one sanitized record and exporting a ZIP with readable TXT,
  structured JSON, safe system/application information, and a README.

Verification:
- [x] Retention, corruption recovery, event bounds, redaction, copy, export,
  first-screen/wizard visibility, processing events, and packaged-entrypoint
  wiring have automated coverage.
- [x] Package the journal and its connected initial-screen/wizard actions in the
  verified Windows `3.0.1` build.
- [ ] Confirm the journal layout and exported ZIP manually in the packaged
  Windows application.

### Task 63 - Security Review And Production Readiness

Status: Planned

Scope:
- Review authentication, key storage, signing, database access, rate limiting,
  audit privacy, backup restore, incident response, and dependency risk.
- Resolve all high-severity findings before production deployment.
- Production deployment, credential creation, and DNS changes require explicit
  owner approval.

### Task 64 - Proactive Cross-Component Contract Audit

Status: Local audit complete - Windows and live-account acceptance pending

Implemented:
- Align V3 generated-path validation with the worker's `output/.run` run workspace.
- Make native stop-after-current terminal even when the stop marker follows a
  successful output event; pending items are cancelled instead of left running.
- Keep incomplete evidence fields as `unknown`/`None` instead of converting them
  to clean/zero results.
- Remove the legacy sensitive `licenses.db` from Git tracking while preserving
  the ignored local copy for the configured local/server workflow.
- Synchronize offline fixtures with the protected opener and run-workspace
  contracts without making real provider requests.

Verification:
- [x] Focused regressions cover output-path trust, stop-after-current, incomplete
  evidence, provider routing, and metadata-preserving outputs.
- [x] Full local pytest and full `compileall .` checks.
- [ ] Windows packaged, DPI, installer/UAC, real-account, live provider, and
  native teardown checks; these remain `WINDOWS_REQUIRED` or `BLOCKED`.

### Task 65 - Windows 3.0.1 Acceptance Fix Pack

Status: Azure 3.0.2 installer built; Windows acceptance pending

Source of truth:
- `docs/testing/windows-3.0.1-acceptance-checklist.ru.md`

Required for the next Windows build:
- Replace the misleading offline saved-license key prompt with a fail-closed
  server-unavailable state and retry action.
- Disable and explicitly mark the remaining SynthID consent control as
  unavailable.
- Keep the processing file list and model synchronized after `process more`;
  preserve selected inputs until the user removes them.
- Simplify and make the wizard header responsive; remove the false dirty label
  and surface only real autosave failures.
- Lazy-load and cache wizard pages, keep hardware probes off the UI path, and
  show determinate progress for initialization that is visibly slow.
- Use one consistent processing editor presentation across modes and replace
  avoidable user-facing technical English.

Deferred follow-up:
- Simplify the prompt-generation workflow without changing it in the 3.0.1 fix
  pack.

Required regressions:
- Saved activation plus network/server outage never reopens key entry and never
  grants access.
- SynthID remains disabled and labelled unavailable in every mode.
- `process more` has matching visible/model file state and supports reprocessing
  the same input.
- Header actions fit the minimum window at supported Windows DPI values.
- Autosave failure is visible; successful autosave has no false dirty status.
- Initial mode selection creates only required pages and hardware probes cannot
  block the GUI thread.
- Shared processing labels and capability states match across all three modes.

Implemented for candidate `3.0.2`:
- Route only typed temporary license-service failures to Retry/Close; rejected,
  expired, revoked, or otherwise invalid saved activations can open the safe
  replacement-key flow without granting access.
- Keep selected processing inputs synchronized for `process more`; disable and
  label SynthID consistently; localize shared cleanup copy.
- Simplify the work header and show only real autosave failures.
- Construct only the selected mode and requested pages, cache successful pages,
  show determinate initialization progress, and retain failed factories for a
  bounded user-visible retry.
- Synchronize `release/VERSION.txt` and the manual Azure pipeline default at
  `3.0.2`; the pipeline remains build-only with `trigger: none` and `pr: none`.

Verification:
- [x] Focused acceptance regressions: 81 passed, 14 subtests passed.
- [x] Azure offline release-gate command: 49 tests passed, 1 expected skip.
- [x] Supported source tree passes `compileall`, sensitive-artifact scan, and
  `git diff --check`.
- [x] Full suite excluding two documented pre-existing baseline inconsistencies:
  517 passed, 1 expected skip, 4 deselected, 73 subtests passed.
- [x] Manual Azure run `77` (`20260820.1`) succeeded from source commit
  `92046e0`; artifact `windows-installer` contains
  `VibixImages-Setup-3.0.2.exe` (`164809973` bytes) and matching SHA-256
  `46366a1a655e3f272e7bff54674e14c66036d468bdd93e46f2cceaa9fd21fc14`.
- [ ] Repeat focused Windows installation, licensing, DPI, retry, and update
  acceptance against the exact Azure artifact and its SHA-256.

### Task 66 - macOS Azure Release

Status: Azure artifact verified; Mac acceptance pending

Implemented:
- Add a separate manual Azure pipeline for an unsigned `macos-x64` `.app`
  distributed as a ZIP archive with a SHA-256 sidecar. It runs natively on
  Intel Mac and through Rosetta 2 on Apple Silicon because Azure's hosted
  ARM64 preview is currently paused.
- Bundle the verified universal Real-ESRGAN macOS runtime and select its native
  executable name at runtime.
- Request platform-specific update manifests; accept only ZIP updates on macOS,
  verify their signed metadata and SHA-256, and reveal the archive in Finder for
  manual replacement.
- Use `~/Library/Application Support/Vibix Images` consistently for macOS config,
  API credentials, license state, diagnostics, and update downloads.

Verification:
- [x] Full Linux-safe suite: 534 passed, 1 expected platform skip, 2 deselected,
  plus 73 unittest subtests.
- [x] Real-ESRGAN macOS archive SHA-256 and universal arm64 slice verified.
- [x] Azure run `91` succeeded from source commit `6b41682`; artifact
  `macos-x64` contains `VibixImages-macOS-3.0.2-x64.zip` (`245630259` bytes)
  and a matching SHA-256 sidecar:
  `04d4bf58f085f5239a7a6a5c46c3b6470d32ee6d116828ee383d29708399f6d9`.
- [x] The downloaded ZIP passed `unzip -t`; the application launcher and bundled
  Real-ESRGAN executable are Mach-O x86_64 binaries with executable permissions.
- [ ] Manual Gatekeeper acknowledgement, launch, licensing, provider, and update
  acceptance on Apple Silicon hardware.

### Task 67 - Windows Local Processing Repair

Status: Source fix verified; Windows Azure rebuild requires explicit owner approval

Implemented:
- Replace the incomplete Windows Real-ESRGAN `v0.2.0` archive with the official
  pinned `20220424` archive containing the executable, DLLs, and model files.
- Validate the archive SHA-256 and required 2x/4x model files before packaging;
  reject incomplete or unsafe ZIP content.
- Correct the 2x clipart model name to the model actually included in the
  runtime: `realesr-animevideov3-x2`.
- Collect rembg sessions and metadata in PyInstaller and add a packaged local
  runtime smoke gate that checks both Real-ESRGAN resources and rembg imports.
- Keep safe local/provider failure details in diagnostics, including bounded
  task ID, provider error code, and sanitized error message.
- Temporarily remove the non-functional BEN2 choice from that release candidate.
  Task 70 supersedes this limitation by packaging the pinned BEN2 runtime and
  restoring the provider with an explicit first-download notice.

Verification:
- [x] TDD regressions observed failing before each implementation and passing
  afterward.
- [x] Official Windows Real-ESRGAN archive SHA-256 verified as
  `abc02804e17982a3be33675e4d471e91ea374e65b70167abc09e31acb412802d`;
  the preparation script staged all required runtime files.
- [x] Real Local rembg IS-Net inference produced a valid RGBA output with an
  alpha range of `(0, 255)` using a temporary model cache.
- [x] Full Linux-safe suite: 545 passed, 1 expected platform skip, 2 deselected,
  plus 73 unittest subtests.
- [x] Expanded manual Azure release-gate equivalent: 94 tests passed, with the
  expected Linux Real-ESRGAN and absent sibling-service skips.
- [x] `compileall`, sensitive-artifact scan, PowerShell syntax, and
  `git diff --check` passed.
- [ ] Run a new manual Windows Azure build only after explicit owner approval,
  then retest Local Real-ESRGAN and Local rembg in the packaged application.

### Task 68 - Results State And Actionable Diagnostics

Status: Source fix verified; packaged Windows acceptance pending

Implemented:
- Keep the shared `Запустить` navigation action out of the Results state so its
  retained keyboard focus cannot reset the workflow to mode selection.
- Show a separate `Завершить и на главную` action only after the queue reaches
  a terminal state; worker completion itself remains on Results.
- Record ordered, privacy-safe run events with sequence number, elapsed time,
  operation ID, mode, enabled stages, provider/model routes, per-stage status,
  output filename/size, terminal counts, and sanitized technical errors.
- Record workflow step changes and explicit Results exits so support can tell
  whether the application navigated because of a user action.
- Reserve room for one `log_truncated` marker when the bounded journal reaches
  its size limit.

Verification:
- [x] TDD regressions failed before implementation and pass afterward for the
  Results transition, Trim + 300 DPI event trail, provider/model routes,
  sanitized errors, explicit screen exit, and truncation marker.
- [x] A real WorkerThread Trim + white-background + 300-DPI run created the
  expected PNG and produced ordered Trim, DPI, output, and terminal events.
- [x] Full unittest suite: 530 passed, 2 expected environment/platform skips.
- [x] `compileall` and `git diff --check` passed.
- [ ] Verify the Results screen and exported diagnostic ZIP in the next
  explicitly approved Windows Azure build; no Azure build was started here.

### Task 69 - Local Processing Release Readiness

Status: Windows target acceptance failed; replacement source fix verified

Implemented:
- Preserve straight RGB under soft alpha in Local Real-ESRGAN, validate projected
  output dimensions/pixels and the selected model before launch, and terminate a
  hung process on cancellation or the bounded timeout.
- Add the Photo model to the Windows runtime gate and strengthen macOS checks for
  both slices of the universal runtime.
- Make rembg profile presets select their documented models and show the first-run
  model download sizes in the dropdown.
- Emit exact background-removal stage states, retain safe DPI failure causes, redact
  token-like output names, and reset retry progress correctly.
- Restore legacy processing choices when V3 preferences do not yet exist and verify
  a real QThread Trim + 300 DPI run reaches terminal Results with a valid output.
- Exercise a tiny rembg inference in packaged Windows and macOS smoke checks.

Verification:
- [x] Full unittest suite: 543 passed, 2 expected environment/platform skips.
- [x] Full pytest suite: 570 passed, 1 expected platform skip, 2 deselected,
  and 73 subtests passed.
- [x] `compileall`, sensitive-artifact scan, and `git diff --check` passed.
- [x] Azure Windows run `102` and macOS run `103` succeeded from source commit
  `a085167`; both downloaded artifacts match their SHA-256 sidecars.
- [x] Windows run `102` target testing exposed a Local rembg ONNX Runtime DLL
  initialization failure and confirmed that Local BEN2 was absent from release UI.
- [ ] Replace Windows run `102` through Task 70, then perform focused
  local-processing and Results/diagnostics acceptance before publication.

### Task 70 - Installed Local Background Runtime Repair

Status: Automated release verification complete; owner target testing pending

Implemented:
- Restore `Local BEN2` in the provider selector and preserve existing BEN2
  settings instead of silently migrating them to rembg.
- Use the official BEN2 ONNX model pinned to revision `e48a207` and exact
  size/SHA-256 instead of adding the incompatible, much larger PyTorch runtime.
- Explain before use that BEN2 downloads an approximately 230 MB model once,
  needs internet for that first download, should have 300 MB disk space, and
  needs approximately 4 GB of free RAM during CPU processing.
- Extend the packaged local-processing gate through a real BEN2 ONNX model load and
  inference, in addition to the existing Real-ESRGAN and rembg checks.
- Bundle Microsoft's signed Visual C++ x64 runtime required by ONNX Runtime,
  exclude PyInstaller's shadowing standard-name VC runtime copies recursively
  while preserving private hash-named libraries, replace stale native files
  atomically on upgrade, and preserve user settings stored outside the
  installation directory.
- Install the completed Windows installer into an isolated Azure path and run
  release plus local-processing smoke checks from that installed copy.
- Collect SciPy's dynamically imported Array API compatibility modules required
  by rembg in the Windows PyInstaller package.
- Provide writable null standard streams in a windowed Windows process so rembg's
  first-model-download progress cannot fail when no console is attached.

Verification:
- [x] TDD regressions failed before implementation and pass afterward for BEN2
  selection/help, pinned build dependencies, rembg import, installer cleanup,
  prerequisite inclusion, and installed-artifact Azure verification.
- [x] Full unittest suite: 557 passed, 2 expected environment/platform skips.
- [x] Full pytest suite: 584 passed, 1 expected platform skip, 2 deselected,
  and 73 subtests passed.
- [x] `py_compile`, PowerShell parsing, model pin/size/hash verification, and
  `git diff --check` passed.
- [x] Real official BEN2 ONNX inference completed with a valid `64x64` RGBA
  result and alpha range `(0, 255)` using bounded ONNX Runtime session options.
- [x] Azure Windows run `116` succeeded from commit `6ed1537`; its installed-copy
  gate validated the bundled Local Real-ESRGAN runtime and performed real rembg
  and BEN2 inference.
- [x] Azure macOS x64 run `117` succeeded from the same commit; its packaged
  release and local-processing gates passed.
- [x] Downloaded artifacts match their SHA-256 sidecars; the macOS ZIP also
  passes `unzip -t`.
- [x] GitHub Windows run `32900235313` succeeded from commit `44ec8a7`; the
  downloaded `VibixImages-Setup-3.0.5.exe` is `191303609` bytes and matches its
  SHA-256 sidecar (`bbd4bfcbb952bdf10a7b606671b1177be02ed8da47215d1abf8f6dccb3e50978`).
- [x] Replacement GitHub Windows run `32977293110` succeeded from merged
  `develop/3.0` commit `5732eedd71420b80400fc8b15d10b34c989dc888` while macOS was
  skipped. The workflow installed the completed package and verified the
  installed application's mode artwork and prompt-screen evidence. The
  downloaded installer is `191362608` bytes with SHA-256
  `6c3f4837b381f2da44cd0d54fa4b8fce8ec03b047227efc9e3b57c226d8daba6`.
- [ ] Perform focused visual and production-license acceptance on the owner's
  Windows computer before uploading a 3.0.5 server revision.

### Task 71 - Branded Three-Stage Windows Installer

Status: Source implementation verified; Windows build requires explicit owner approval

Implemented:
- Keep Inno Setup as the installer engine and use its built-in high-DPI Polar
  dark style with a styled title bar, graphite background, and no third-party
  style dependency.
- Present the flow as `Добро пожаловать → Установка → Готово`, simplify button
  text, hide the redundant Start Menu and Ready pages, and preserve destination
  and desktop-shortcut choices in the installation stage.
- Continue using the approved hash-locked `assets/installer-wizard-hq.png`.
- Pin Inno Setup 6.7.1 in both Windows build workflows so the dark-style
  directives compile reproducibly.

Verification:
- [x] New regression tests failed against the old installer configuration and
  passed after implementation.
- [x] Branding and release-entrypoint unit tests pass; `git diff --check` passes.
- [ ] Compile and visually inspect the installer on Windows in a separately
  approved build. No Windows build was started for this task.

### Task 72 - Provider-Aware Source Verification

Status: Source verification complete; review and target-Windows acceptance pending

Verified source behavior:

- KIE and PhotoRoom have independent settings limited to 1, 2, or 3 active
  tasks, each defaulting to 3. The shared fixed release cap is 6 simultaneous
  network tasks.
- KIE generation, Topaz, KIE background removal, and other existing KIE work
  share the KIE limit. PhotoRoom has its own launch guard: an initial burst no
  larger than its selected limit, then a sustained 60-images-per-minute pace;
  bounded HTTP 429 handling remains visible.
- Local processing remains sequential. Recraft payload, availability, and
  no-silent-fallback behavior are unchanged; fal.ai remains excluded.
- Results and diagnostics retain the exact item index for concurrent events and
  keep prompts, credentials, raw provider responses, and full private paths out
  of user-facing diagnostics.

Verification:

- [x] Focused offscreen settings, scheduling, queue, navigation, completion,
  provider-contract, diagnostics, and installer-artwork regressions: 292 passed
  and 24 subtests passed.
- [x] Full offscreen pytest suite: 724 passed, 1 expected Linux skip,
  2 deselected, and 87 subtests passed.
- [x] `python -m py_compile main.py runtime_settings.py v3_api_settings.py`,
  tracked sensitive-artifact scan, and `git diff --check` passed.
- [x] No paid provider request, build, merge, server publication, or push ran.
- [ ] Obtain review, then separately approve a Windows-only build and
  target-Windows acceptance before any server revision publication.

### Task 73 - Conditional Reference Generation Settings

Status: Integrated, source verified and packaged; owner acceptance pending

- [x] Label the primary generation settings with the number of prompts without
  references.
- [x] Hide reference-generation settings when no prompt has references.
- [x] Show and label the reference-generation section with its prompt count
  when references are present.
- [x] Verify Clipart and Pinterest regressions, Python compilation and the full
  offscreen test suite.
- [x] Integrate after owner approval and include the fix in the replacement
  Windows build before publication.
- [x] Verify the integrated source with the full offscreen suite: 738 passed,
  1 expected Linux skip, 2 deselected, and 87 subtests passed.
- [x] Build and install-check Windows 3.0.5 in GitHub Actions run `33032049521`.

### Task 74 - Reference Preflight, Friendly KIE Errors and Review Alignment

Status: Integrated, source verified and packaged; owner acceptance pending

- [x] Reject a local reference larger than 10 MB at attachment time and show
  its name, actual size and corrective action.
- [x] Reject oversized references already stored in older projects before any
  paid provider task is created.
- [x] Keep HTTPS references free of hidden downloads and classify KIE
  insufficient-credit and oversized-reference failures for the user.
- [x] Align the Review summary at the top-left with consistent row spacing.
- [x] Verify focused Clipart/Pinterest/Results tests, full offscreen pytest,
  Python compilation and diff integrity.
- [x] Integrate after owner approval and include the fix in the replacement
  Windows build before publication.
- [x] Verify the integrated source with Python compilation, sensitive-artifact
  scan, diff integrity, and the full offscreen suite.
- [x] Include the fix in the installed-artifact checks and uploaded installer
  from GitHub Actions run `33032049521`.

### Task 75 - Pinterest Prompt-Only MVP

Status: Implemented on feature branch; owner acceptance pending

- [x] Replace the active six-template/product flow with ready prompt or CSV
  input, editable prompt/reference review, model selection and generation.
- [x] Set Pinterest default to vertical 2:3 and keep image processing hidden.
- [x] Reuse the shared generation queue, KIE/Fal routing, cost preflight and
  result folder instead of maintaining a second Pinterest worker contract.
- [x] Update RU/EN localization, PRD and backlog to match the approved scope.
- [x] Verify focused offscreen tests, compilation, and `git diff --check`.
- [ ] Perform manual owner acceptance in the desktop app; do not run paid API
  calls or publish a build without explicit approval.

### Task 76 - Temporarily Hide Alpha Brush Editor

Status: Implemented on feature branch; owner acceptance pending

- [x] Hide the Clipart result-page alpha/transparency brush editor in the
  current stable client surface.
- [x] Hide save-corrected-PNG and save-alpha-mask actions together with it.
- [x] Preserve the implementation for the future image-processing release.
- [x] Add a regression test and verify focused queue/navigation checks.

### Task 77 - Fal.ai Transparent Upscale Selection

Status: Implemented and offline verified; live quality and packaging pending

- [x] Offer Fal.ai as a provider for the second upscale after transparent
  background preparation.
- [x] Add documented alpha-safe Fal.ai routes: Bria Increase Resolution (2x/4x)
  and Topaz Transparent (fixed 4x PNG), alongside the existing legacy route.
- [x] Preserve the selected model in project state, worker settings, request
  payload, call-count summary and safe run report.
- [x] Reject non-alpha-safe models after background preparation with a clear
  local preflight error; do not silently substitute a paid provider.
- [x] Make Automatic Clipart use exactly one default pass after background
  preparation; leave the pre-background pass off.
- [x] Verify 45 isolated Fal catalog/provider contract tests plus Python
  compilation and diff integrity without a paid request.
- [x] Run affected Qt/runtime tests and the full offline suite; inspect the
  automatic launch screen at 1120x780 and test model selection after reopen.
- [ ] Check actual upscaled PNG quality with the selected provider and prepare
  updated packaging when separately authorized.

## Auto Clipart style/reference UX, 2026-09-28

- [x] Owner approved style/palette/object mockups and explicit reference source/skip states.
- [x] Implement style samples, combined palette previews, reference source controls,
  skip action, concise planning quote and next-step guidance.
- [x] Remove the stale launch cost tab; show only applicable model controls and quote the effective model and current estimate before generation.
- [x] Run focused offline tests and compare actual 1120×780 Qt screens with mockups.
- [x] Add a native maximize/restore button to the transparency editor window;
  keep its tools visible in the maximized state.
- [x] When the image model ignores the requested key color, try an automatic
  local U2Net cutout with a binary, inset alpha edge; verify on the two supplied
  PNGs and retain manual status if the fallback fails.
- [ ] Run native Windows acceptance for packaged style assets and the full workflow
  before release. No build or paid provider call was authorized in this task.

Evidence and remaining limitations: `docs/ui/3.2/style-reference-ux/README.md`.

## Auto Clipart export workspace, 2026-09-29

- [x] Run the formerly skipped real Real-ESRGAN 2x/4x acceptance locally using
  the official Ubuntu models and temporary software Vulkan; alpha/layout passed.

- [x] Owner approved a single step-8 export page with hover previews, set
  editing, creation and deletion.
- [x] Embed the existing quality/export flow into step 8 and remove the
  duplicate read-only tree; preserve project membership across reopening.
- [x] Allow the last set to be deleted without deleting PNG files or silently
  recreating it from the automatic plan.
- [x] Name and rename sets; derive each ZIP filename from the set title.
- [ ] Verify the full page and final ZIP workflow on native Windows before release.

Evidence: `docs/ui/3.2/export-workspace/README.md`.

Remaining-edge blocker: disk full; owner answer pending for cleaning only /tmp/vibix-size-audit/extracted. No product adoption before stable disk, permanent RED/GREEN and negatives.
