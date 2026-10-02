# Ошибки проекта

## white-method-core-packaging-20261001

Первый full после белого метода:2417PASS+278subtests,57skip/21deselected,
2FAIL: exact architecture baseline и shell shared-import inventory. Новая
v3_processing_flow→white_background зависимость нужна для общей cached-model
readiness валидации; inference только в WorkerThread, лицензированные права и
оплата не меняются. Main и independent source review подтвердили Core boundary.
Добавлена только эта exact pair с review comment; wildcard/расширение слоёв нет.
В build.ps1 добавлен explicit --hidden-import white_background, workflow
implementations по-прежнему исключены. Это правка конфигурации источника,
не запуск сборки. Архитектура/packaging/component/whiteflow36tests PASS7.66s. Независимое
повторное read-only ревью и46tests+9subtests PASS7.56s, замечаний нет.
Новый processing package требует Core3.2.12 и не должен переиспользовать1.5.2.
Release version/workflow dispatch/published manifests не менялись.
Финальный общий прогон после исправлений:2419PASS+278subtests,57skip/21deselected,
392.23s, /tmp/studio-next-final-white-full-green.log. Нерешённых подтверждённых
замечаний этой интеграции нет; native Windows/installed modules не проверены.

## white-background-runtime-integration-20261001

Владелец одобрил mockup «Да устраивает». Registry+shared UI используют новый
local_white_background, current/new rembg cache layouts, cached-only CPU U2Net
loader с MD5 verification. Subclass download_models возвращает найденный файл,
не вызывает pooch; UI проверяет наличие без runtime imports. Worker local
dispatch не попадает в KIE pipeline; одна session переиспользуется. Cancel после
inference предотвращает сохранение; failed item не блокирует следующий.

Actual Qt сравнение выявило несоответствие approved disabled Next: в первом
варианте кнопка была enabled и только click показывал error. Footer теперь
отключает Next при white_background_unavailable; restored selection сохраняется.
Регрессия проверяет disabled click, direct go_next protection и re-enable после
выбора chroma. Новые source/registry fixtures учитывают default upscale_before
и реальный progress contract complete, не succeeded (succeeded относится к
diagnostic event). Первые fixture ошибки не доказательство production дефекта.

107core/runtime/local/metadata tests+6subtests PASS,1skip;79UI/flow/provider
tests+5subtests PASS; отдельный5UI PASS после footer correction. Offline actual
production WorkerThread._process_file_entry, verified cached loader и final PNG
publication: teddy14.531s,knit/pine9.1s; sourceSHAunchanged, exactRGB, framealpha0,
alpha только0/255, обе1536×1536. Одна session. pooch.retrieve запрещён; источник
и local caches неизменны. Private evidence: artifacts/studio-next-candidate/
white-worker. Ideal alpha/все белые детали/Windows пока не подтверждены.

## white-pipeline-dpi-preservation-20261001

Новый реальный worker export fixture выявил исходный240DPI→missing при обычном
PNG сохранении. Причина: _get_png_save_kwargs передавал DPI только внутри
_metadata_cleanup_requested(), даже когда preserve_dpi=True. Первая правка
preserve_colour_metadata только в white intermediate save не решила конечный
export: final stage повторно вызывал общий PNG writer и терял DPI. Новые данные
локализовали общую причину; optional writer parameter удалён. Source DPI теперь
передаётся независимо от cleanup при preserve_dpi, explicit300 override остаётся
приоритетным. Exact runtime output240DPI+ICC/RGB/source unchanged, explicit300
и preserve_dpi=False регрессии PASS. Existing metadata/local tests PASS.

## white-background-offline-20261001

Проверены не только supplied mask contracts, но и настоящий offline rembg/U2Net
на двух исходных white-paper RGB PNG1536×1536 (teddy, knit/pine). Модель уже
скачана в /tmp/clipart-u2net/models/u2net/u2net.onnx; MD5 совпадает с rembg
60024c5c889badc19c04ad937298a77b. download_models возвращает этот файл, pooch
retrieve заменён запретом загрузки; зависимости и production не менялись.
Результаты:4.938s/5.084s, RGB каждого пикселя exactsource, alpha только0/255,
frame transparent, sourceSHAunchanged и saved PNG reopen exact PASS. Actual
opaque Qt previews показывают сохранение основных деталей, но местами светлый
ободок; ideal semantic alpha не известна. Это не подтверждение идеального края,
не Windows-приёмка и не запуск UI/worker. Core33tests PASS, visual approval
нового provider pending. Private evidence в artifacts/studio-next-candidate/
white-background основного проекта, пользовательские PNG не добавлены в Git.

## candidate-local-https-environment-20261001

Combined admin→signedfeed→Qt test сначала не стартовал: desktop venv не имеет
psycopg, затем restricted sandbox запрещал localhost socket. Никаких исходных
правок или новых зависимостей: добавлен путь уже имеющегося temporary server
venv для psycopg; разрешён isolated localhost fixture run. Финально1PASS2.24s,
/tmp/studio-next-real-upcoming-https.log. Это environment setup failures, не
дефекты production; тест не ослаблен. Fixture не использует настоящие ключи,
лицензии, business data или рабочий server.

## local-contour-steps-20260930

Владелец заменил три силы обработки на небольшие фиксированные повторяемые
шаги; отдельные кнопки отключаются при пределе и пересчитываются после изменения
выделения/правки/Undo. Updated UI mockup без силы показан в
artifacts/local-contour-steps-mockup основного проекта. Владелец ответил
«Да, реализовать», 2026-10-01; UI в работе, геометрия проверяется отдельно.

Первая геометрическая версия: Simplify<=0.5px, global simple-path guard.
Known synthetic tests прошли, но main проверка настоящего auto-contour утёнка
показала оба действия no-op. Current real14/current.png (private evidence в
artifacts/transparency-controls-check/controls-agent), actual extractiontol1:
9paths,950nodes вглавномpath,73selected footnodes. Проблемы разделены:
1. Минимальная удаляемая nonsharp-девиация0.85px, уже больше начального шага:
   исходный auto-contour сам приближает границу с допуском1px. Такой preset
   также не упрощал141node/26selected контур одобренного mockup.
2. Global_simple отвергал9контактов исходного pixel-trace, часть вдалеке от
   выделения. Это не доказывает небезопасность любого локального изменения.

Новые данные обосновывают подбор preset по существующему auto-tolerance и
защиту геометрии исходных контактов до/после вместо полного запрета любой
самокасающейся исходной границы. Новые контакты/пересечения запрещены; отверстия,
кончики, границы выделения, untouched handles остаются защищены.
Фиксированный шаг Simplify1.25px выбран по реальным контурам: лапка73→65,
mockup26→24; Smooth двигает anchor не более0.35px за нажатие и достигает
безопасного предела. Геометрический root-прогон24local+42existing=66tests PASS.
Независимое ревью выявило P3: почти прямой explicit handle мог превысить
1.25px на0.0002923px, хотя anchor укладывался в допуск. Исправлено проверкой
расстояний всех control points обеих исходных cubics до нового segment;
convex hull даёт консервативную границу всей кривой. Exact fixture включён
в регрессионные тесты. Независимая проверка выявила P2: расстояние до
бесконечной прямой допускало срез выступа2.119px за endpoint нового сегмента.
Исправлено отдельной clamped-projection distance_to_segment, добавлен точный
fixture. Повторный root-прогон66tests PASS; независимая перепроверка41tests PASS
и оба отдельных reproductions PASS. Нерешённых геометрических замечаний нет.

UI независимое ревью и root-repro выявили P2: при нескольких выбранных
контурах overlapping support второй path записывал исходные alpha поверх
первой правки. Synthetic100×100, две отдельные детали с зазором3px:
A-only меняет3pixels y41,x44..46; совместное применение сохраняет0 из3;
перестановка paths меняет итог в6pixels. Причина: assignment полного support,
а не только фактически изменённых candidate pixels. Передано на исправление
с регрессией сохранения обеих правок и независимости от порядка. Результат
повторной проверки: worker-regression сохранения обеих правок/порядка PASS;
root и независимая финальная перепроверка ещё ожидаются.

UI независимое ревью и root через настоящий QTest mouseClick выявили P2:
после local preview кисть удаляет pixel35,20 (mask=0, rendered=0), но
переключение До→После показывает старую preview-alpha255. Cache/async guard
учитывал только paths, а не исходную mask revision. Передано на исправление
с проверкой brush/Undo/Redo, актуального preview и совпадения Apply с After.
Исправлено mask_revision guards, invalidation/recompute после кисти/Undo/Redo;
Qt-regression PASS.

Inherited hole-edit P2: выбранное отверстие меняло vectors, но не alpha.
Parent exterior считался защищённой отдельной деталью; после исключения
ancestor выяснился второй блокер: весь материал вне old-hole ошибочно
считался residual. Hole expansion теперь удаляет материал окружения,
contraction сохраняет alpha вложенных островков (root fixture77→255 до
исправления,77→77 после). Ancestors исключаются из other-path protection;
child/neighbour paths защищаются. Root тесты expansion/contraction и
несколько уровней outer/hole/island/hole, Qt preview/Apply/Undo прошли.

Финальное независимое ревью выявило stale proposal после кисти: raw77 pixel
alpha[43,45] в cleared3×3 gap не имел BezierPath и удалялся77→0 при
hole expansion. Новые данные требуют component ownership, а не только
список путей. Теперь ближайший enclosing exterior определяет окружающий
материал через8-connected flood fill по current alpha; отдельные компоненты
защищены даже без контурных точек. Exact fixture и positive connected-material
сценарии проверены root; независимая финальная перепроверка60tests PASS:
raw77→77, connected material77→0, ordinary hole expansion3pixels.
Открытых подтверждённых замечаний нет.

Полный safe pytest после всех исправлений:2219PASS+278subtests,57skip,
20network/paid deselected; один FAIL в старом cancellation/timer test:
QTest.qWait(40) не привёл к timer tick (ticks пуст). Целевой166-test run
раньше проходил этот сценарий, отдельный повтор после full тоже PASS0.77s.
Производственная причина пока не подтверждена; возможна зависимость от
нагрузки/очереди событий. Тест и его40ms проверка не ослаблены, source для
этого failure не менялся. Повтор полного прогона без параллельных проверок
завершён:2220tests+278subtests PASS,57skip,20deselected,241.59s.
Первый full остаётся записанным FAIL; transient причина не подтверждена.

ROI allocation bounds не дают разрешения менять все пиксели прямоугольника:
раздельные выделения/длинные дуги могут окружать невыделенную шерсть. UI должен
ограничить фактическое применение support изменённых сегментов, сохраняя
невыделенный raw alpha, даже когда он отличается от приближённого старого пути.



## pale-material-policy-fix-20261001

После отклонённых gamut/scale guards источник ошибки пересмотрен: локальная
опора принадлежит связанному, но другому материалу. Дополнительный поиск
реальных deeper samples и brightness-only fit исправляет real13, но оставляет
6thin cases без чистой глубокой опоры и увеличивает148tests10.77→31.26s.
Same-depth/tangent материал также не доказывает происхождение RGB: настоящая
засветка может дать идентичную полосу. Такой поиск в production не перенесён.

Владелец ранее разрешил сохранять исходный оттенок при неоднозначности и
2026-10-01 поручил закончить исправления до сборки. Минимальная policy:
opaque candidate, невозможный convex recoveredRGB вне[-2,257], обе nonkey
компоненты>=230,RGBspread<=24,keychannel не доминирует → не применять
сомнительное вычитание key. Один helper применяется к early_rim и
refine_edge_mixture; новые scale ограничения и source-reference search не нужны.
Реальные control13pixels402126/376129/359148 теперь sourceexact на8этапах.
Image13/07:1254pxRGBA,transparent frame,PNG roundtrip exact,SHAoriginal unchanged.

Исправление подтверждено187tests:148existing +39new. Newthin known-truth27cases,
bright-coloured additive3keys,ordinary pale coverage.8/.85,ambiguous flatpaint.
Релевантный baseline с выключенным helper воспроизводит18thin failures.
Первый новый stage-observer test ошибочно предполагал обязательный staged
route:27KeyErrors вместо доказательства RGBdefect. Исправлен harness: отдельно
реальный staged solver и automatic solver, новая защита не менялась.

Дополнительный known-truth weak.95 mixture FAIL одинаково baseline/fixed:
(238236233,255) вместоclean249246233/alpha242. Оно неотличимо от opaque painted
flatband; existingflat-protection и opaque background threshold сохраняютsource.
Это не объявлено correctedalpha. Отдельная paint-ambiguity regression защищает
согласованный prior сохранения source; обычные.8/.85 mixtures проверены как
реальные partial. Яркая nearwhite additive также может остаться. Полное
различение этих происхождений по одному изображению не подтверждено.

Algorithm identity повышена v9→v10; receipt read не перемаркирует v9.
Первый contract run40PASS/1FAIL+9subtests из-за фиксированного expectedv9;
обновлён exactexpectedv10 и добавленv9 в backward-readable cases.
После этого41tests+9subtests PASS. Ошибочный ранний fullrun прерван (exit130),
не засчитан как PASS; финальный fullrun начат после исправления contract.
Independentreview73tests PASS в другом установленномQt venv, source не менялся.
Future release нуждается в новом image-processing payload: опубликованный
1.5.2 содержит старый алгоритм; обновление только Studio не гарантирует этот fix.
Processing workflow с direct-entry также требует нового payload и корректного
minimumCore. Официальные пакеты/версии не строились и не публиковались.
Evidence: /tmp/studio-next-pale-final.log, /tmp/studio-next-component-contracts-final.log,
artifacts/studio-next-candidate/edge-colours/verification.json основного проекта.

## candidate-upcoming-grid-20261001

Совмещение ранее проверенных upcoming карточек и fixed-size adaptive grid
в новой ветке обнаружило regression: после withdrawal новых карточек сетка
возвращалась к фиксированным3колонкам даже на1920px. Причина: старый
set_upcoming_cards вручную раскладывал index//3, не используя новый общий
_layout_module_cards. Actual Qt regression воспроизвёл position(1,1)
вместо(0,4); после перенаправления на общий layout90target tests PASS.
Поведение опубликованного сервера/лицензий не затронуто; будущие карточки
не получают action signals и не меняют права существующих модулей.
Evidence: /tmp/studio-next-catalog-integration.log; regression
 tests/test_studio_upcoming_ui.py::test_promotional_refresh_keeps_wide_grid_and_compact_cards.

## pale-rim-followup-20261001

Диагностика13d30af без production правок. Original13/07 неизменны и не
добавлены в Git. Изменения алгоритма и регуляторов сначала обсуждаем.

Подтверждение: opaque светлая полоса1–2px рядом с бежевым материалом
перекрашивается при удалении blue/red/green key.27synthetic cases
(3colours×3widths×3keys): baseline повреждает18cases, width3passes.
Source(241,241,226,255)→staged(241,241,139,255). Малая fit ошибка с соседним
материалом не доказывает его принадлежность той же детали.
Наreal13:402,126 source(241,241,226,255)→final(241,240,130,255);
376,129 source(245,245,241,255)→final(245,245,203,255).
Early fit первого scale1.3603/background.2043 даёт recovered
(302.894,302.380,219.066), второго scale1.2560/background.1483 даёт
(287.673,287.324,238.910). Out-of-gamut возможен и при настоящей additive засветке.

История offline экспериментов, функции подменяются только в памяти:
1. Gamut guard early_rim → staged thin-paint27/27 и57local-material tests PASS.
   Real376,129 сохранён;402,126 желтеет на следующем refine_edge_mixture.
2. Opaque gamut guard также в refine_edge_mixture → контрольные real pixels
   сохранены,142tests PASS/6FAIL. Отклонён: ломает genuine additive spill.
3. Новые данные: прежние additive controls имеют foreground coefficient<=1,
   светлые материалы >1. Узкий guard сохраняет opaque pixel при невозможном
   convex восстановлении и scale>1.01, оставляет старую обработку при меньшем
   scale; early_rim также требует background<1.148tests PASS, отдельно полный
   automatic pipeline27/27known-truth PASS. Real402,126/376,129/359,148 сохраняют
   sourceRGB на всех наблюдаемых этапах. Production не изменён.

Независимое read-only ревью: scale включает brightness и coverage относительно
заимствованной опоры, поэтому1.01 эвристика. Reference(180,150,50),
observed(234,195,129), key(0,0,255) могут быть bright+additive смесью сscale≈1.3.
Новый guard способен оставить такую засветку. Нужны совместные bright-additive
и near-threshold tests, отдельные stage regressions. Это подтверждённый риск
кандидата, не новая подтверждённая ошибка production.148tests не покрывают его.
Reviewer не запускал тесты; primary проверил отдельные27full-pipeline cases.

Primary дополнительно проверил18known-truth additive-only cases:
brightness .99/1/1.009/1.011/1.02/1.3 ×3RGB-key permutations,
key(20,45,240), reference(180,150,50), source=brightness*reference+.25*key.
Baseline15/18 и narrow18/18 имеют RGBerror>3. Приbrightness1.3 baseline
refine_edge_mixture даётclean(234,195,65,255), narrow сохраняет загрязнённый
source(239,206,125,255): подтверждена регрессия кандидата. При меньшей
яркости оба путают additive с convex mixture; это неоднозначность модели,
не доказательство применимости к real13. Порог1.01 не считается решением.
Следующая правка не предлагается наугад: нужен критерий материала/локальной
опоры и контроль bright-additive одновременно со светлой краской.
Evidence: threshold-additive-probe.json. Production неизменён.

Experimental13/07:1254×1254RGBA,PNG roundtrip exact,SHA источников неизменны.
Идеальная alpha/cleanRGB реальных изображений неизвестны. Это не Windows
приёмка и не подтверждение всех оттенков. Evidence основного проекта:
artifacts/edge-controls-followup-20260930/{narrow-experiment-tests.log,
narrow-known-truth.json,narrow-provenance.json}, воспроизводимые offline scripts.
Нет платных запросов, model downloads, сборок или изменений сервера.

## transparency-controls-diagnostics-20261001

По annotation2 проверены standalone Clipbrook параметры без изменения Studio:
11изображений × (currentPython +12referenceconfigs)=143offline выполнения,
не143теста качества.7knowntruthsynthetics:furRGBkeys,botanical256/512,smooth,
smallislands. Bearpreviouscutout толькоrecompositeproxy;13/07/14realunknowntruth.
Оригиналы иsourceSHA неизменны. Evidence/main report находятся в
artifacts/transparency-controls-check/controls-agent основного проекта.

Reference minIsland800 удаляет742/3600opaque botanicalpixels (20.6%),100→405,
0→0. Main независимо пересчитал эти значения и smooth/furblue current/reference
loss/RGBdamage. mix0/.5/1 повреждает0/13/19knownopaque lavenderpixels;radius24→546.
alphaFloor0 при island0 всё ещё теряет1714/6112partialfurpixels. Частичная средняя
ошибка может улучшиться одновременно с потерей деталей, поэтому meanнедостаточно.
На real13/07/14 нельзя объявить изменения маски доказанным улучшением/ухудшением
без исходной идеальной alpha. Медвежонок на настоящем chromaframe не проверен.

Решение для обсуждения: отделить восстановлениеRGB от alpha/detailloss; не
переноситьminIsland800илиreferenceдиапазоны в Studioкакбезопасныеползунки.
Новыхprodправок/зависимостей не было. Данные пользователя не добавлены вGit.

## module-outline-grid-20261001

Исходная сетка растягивала карточки по ширине при фиксированных3колонках.
Владелец одобрил fixed349×248/112pxartwork+adaptivecentered columns. На первом
варианте resize1120→980→1120 независимое ревью обнаружило history dependence:
две колонки требуют scrollbar, scrollbar сужаетviewport1072→1062, расчёт
сохраняет две колонки даже после возврата1120. Исходный regression проверял
лишь неизменную ширину и не ловил число колонок.
Root fix: maximumViewportSize без текущей полосы, прогноз высоты строк и
reserve scrollbar width только если он понадобится. Усилен regression возврата:
item3 position1,0 и scrollbar hidden.8targetQttests PASS.

Кнопки: существующий card_action отдавал Open при updatehint. По уточнению
владельца actionable Update теперь приоритетен, offline/not-download-supported
оставляет Open. Нетdropdown/автоскачивания. Единичныйclick intent, denied/unknown
и disabled covered. Trusted fresh authorization/package checks не изменены.
105broader tests+10subtests PASS; независимые fresh-check probes изменённыйSHA,
denied иoffline не вызвалиinstall. После geometryfix8targetQt PASS.
Повторное независимое ревью после fix:1120→980→1120,12cardsresize и
12→0→5replacement PASS, подтверждённых нерешённых замечаний нет.
Windowsinstalled и realserver не проверены; сборки/публикации не проводились.


## direct-transparency-entry-20261001

Новый прямой вход не должен зависеть от живой очереди или изменять входной PNG.
Исходные6Qt regressions FAIL до реализации. Восстановление direct editor сначала
FAIL: ProjectState.from_dict переводил любой transparency вRESULTS, поскольку
старый редактор зависел от неперсистентной очереди. Исправление: сохранять этот
шаг для processing.transparency_direct; legacy queue editor всё ещё RESULTS.

Независимое ревью обнаружило:
1. Длинный допустимый stem230: errno36 на transaction backup/optional generation
   sidecar. Первый filename-only budget недостаточен; reserved output stem теперь
   ограничен180 UTF8bytes/UTF16units с запасом на mask/backup. Повторная проверка
   выявила слишком длинный optional source provenance path; только ENAMETOOLONG
   при чтении optional source record допускает отсутствие записи, прочие ошибки
   сохраняются. ASCII/кириллица save/reopen regression PASS, источник неизменен.
2. Clear/remove/restart не очищали input→copy map; повторный импорт заменённого
   исходника открывал старую копию. Очищаем map при явном снятии выбора, тесты
   всех3путей FAIL-сценария→PASS.
3. Повреждённая persisted copy блокировала валидный исходник. Проверяем PNG
   verify/40Мп при восстановлении map; при повреждении открываем исходник и
   показываем статус. Повреждённый файл не удаляется. Дополнительные repro
   выявили CRC-valid повреждённый IDAT и oversized IHDR: verify недостаточно.
   Добавлен fallback при фактическом decode и DecompressionBombError; huge-header
   не требует аллокации. Canvas.set_document очищал уведомление, поэтому статус
   выводится после него. CRC/IDAT, header, видимый статус regressions PASS.

Сохранение копии использует существующую pair transaction для PNG/маски/lineage,
резервирует имена exclusive create и не восстанавливает транзакции входных файлов.
Проверены disk-failure cleanup, одинаковые имена, старые копии, project roundtrip,
старый queue route, источник SHA, active queue gate.139tests+31subtests PASS,
дополнительные host/project/license/queue/runtime122tests+9subtests PASS.
Повторное независимое ревью финального diff: нерешённых подтверждённых
ошибок не осталось, header/IDAT fallback+видимое уведомление PASS.
Actual/approved mockups1120×780: docs/ui/3.2/direct-transparency.
Не проверены installed Windows, kill процесса посреди save и межпроцессные гонки.
Новые transparency algorithms/ползунки не изменены, сборка не запускалась.


## edge-material-reference-20261001

Поручение: сравнить реальные13.png/07.png, убрать паразитный цвет края и не
заходить глубоко в объект. Источники в attachments не изменяются и не
добавляются в Git. Paid/network processing/build/publication не выполнялись.

Подтверждение: opaque_clipart staged_result уже делает белый лепесток жёлтым.
На13.png source pixel(359,148)=(249,246,233,255), baseline=(250,246,137,255).
Deep Gaussian prior включает жёлтую сердцевину: spatial/connected component
сами по себе не доказывают принадлежность той же детали. Synthetic textured
narrow petal baseline106 RGB changes,3RGB-key regressions FAIL.

История диагностики/проверок:
1. Nearest5x5-eroded source prior within12px samecomponent → petal RGB restored,
   144tests+20subtests PASS → independent review обнаружило ошибочную opaque
   alpha на3px смесиcoverage.8/.85 (636pixels): oldalpha204/217 →255.
2. Veto pure convex source mixture vs deep average →9tests PASS → затенённая
   смесь brightness.9 не распознаётся: source(177,160,160) ошибочно alpha255;
   baseline(217,189,140,204). Added6 shading failures.
3. Plane model scale*FG+mix*key vs averaged deep → shading passes,3petal tests
   FAIL. Средняя опора загрязнена смешением разных материалов; не доказательство.
4. Veto against actual deeper source neighbours±3, band ограничен3px →15tests
   PASS → independent width6 probe и mild hue variation обнаружили повторную
   регрессию: чистый образец скрыт за окном/порог3 слишком строг для текстуры.
5. Добавлены фактические nearest deeper cores13/25within32px samecomponent,
   brightness/key plane fit с relative bounded residual (min12,1+.04*signal).
   42tests PASS, включаяwidth3/6/8, shading/hue иred/green/blue. Итоговые
   общие проверки, реальные samples и independent review продолжаются.


6. Independent wide13/14 probes → fixed-depth25core сам загрязнён. Добавлены
   raw source depth6/12/24/32 + adaptive maximum depth каждого component,
   distance ограничен32px.60HEAD comparisons обычной смеси теперь без alpha
   regressions, но actual13pixel снова жёлтый: guard отвергает белую опору.
7. Actualhelper trace: deep(230,203,138), nearestsource(248,240,228) признан
   смесью, хотя восстановленныйRGB для coverage выходит выше255. Добавлен
   физический gamut guard [-2,257] с quantisation allowance. Actual13pixel
   source(249,246,233,255) →fixedexactsource; baseline(250,246,137,255).
   Synthetic bright narrow rectangle failspre_gamut inall3keys →fixedPASS.

Итог:347distinct tests+46subtests PASS (230existingpixeltests +57newtests
+60diagnostics/provenance/benchmark/report tests). Independent157tests и
60HEAD comparisons PASS для ordinary mixture widths3–14/shading/hue.
Real13/07 RGBA1254px actual PNG save/reopen exact, frame transparent, source
SHA unchanged; originals/customer pixels не входят в Git.

Подтверждённый компромисс: source outer3px RGB(244,219,203), core(240,210,155),
key(20,45,240) может быть настоящей светлой краской или additive key light. HEAD
снимает добавочную примесь, новая защита оставляет RGB неизменным. Владелец
согласовал сохранение исходного оттенка при неоднозначности (annotation3),
поэтому этот случай сохранён и защищён тестом painted-edge, а не объявлен
универсально очищенным. Яркая additive кайма может остаться; без данных о
реальном foreground оба происхождения из одногоRGB различить нельзя.
Полное качество всех фрагментов/installed Windows не подтверждено.

Один общий запуск tests/test_chroma*.py завершился exit143 без итогового
summary; не засчитывается как PASS. Отдельный целевой предыдущий запуск
239tests+28subtests PASS. Финальные проверки относятся к последней правке.
Evidence основного проекта: artifacts/user-edge-colors/baseline и/final,
comparison.png,verification.json; логи /tmp/edge-color-source-final-tests.log.

UI: прямой вход сейчас привязан к queue results. Первый mockup рядом с
«Выбрать файлы» отклонён владельцем; revised left-menu mockup показан, approval
ожидается. Source UI не изменён. Прямой вход должен возвращаться к input files,
не выставлять промежуточным шагам статус пройденных и сохранять copy.


## ctrl-wheel-zoom-20260930

Поручение: Ctrl+колесо должно приближать/отдалять в проверке прозрачности.
Причина отсутствия: inline TransparencyCanvas не переопределял wheelEvent,
Ctrl+колесо передавалось QGraphicsView как прокрутка; Ctrl+/− уже использовал
zoom_requested→_cycle_zoom. Regression до правки3FAIL/1PASS подтвердил отсутствие
zoom в brush/pen и partial detents.
Исправление: wheelEvent с Control направляет событие в существующий общий zoom
путь. Detents120 накапливаются, при смене направления остаток сбрасывается;
pixelDelta поддержан, zero delta не масштабирует; без Ctrl стандартная прокрутка.
Финальные42tests PASS через настоящие viewport QWheelEvent; маска, Undo,
выбор zoom preset, пределы10–1600%, fit и обычная прокрутка проверены.
Evidence:/tmp/ctrl-wheel-zoom-tests.log. Native Windows/input device не проверены.


## contour-edge-specks-20260930

Симптом владельца: после редактирования Безье и сохранения PNG точки вдоль
бывшего края. Исходный PNG не получен, точное совпадение со скриншотом не
подтверждено. Подтверждён сходный программный дефект: circle128/r45, extract
tolerance1, shrink nodes0.85 оставляет26 pixels/20 маленьких островков.
Причина: упрощённый старый контур не покрывает все пиксели исходной границы;
symmetric difference сохраняет их как raster residual. UI overlay в PNG не пишется.

История проверок и уточнений:
- Regression tolerance0.5/1/2 до правки:3FAIL. Первое ограниченное исправление
  hard edge прошло66tests, independent review нашло feather1/2 остатки248/352pixels.
- Relative coverage loss убирает feathered old alpha полностью при new coverage0.
  Начальный ownership через залитый exterior ошибочно удалял отдельный пиксель77
  внутри отверстия; root red подтвердил. Verified source geometry +8-connected
  floodFill сохраняет этот пиксель и соседние детали; regression PASS.
- Independent review нашло full/local mismatch при tolerance>=2; all-node root
  regression после padding10 ещё нашла1pixel при tolerance8/feather1/2. Диагностика
  показала clipping в fillPoly у границы ROI. Финально padding13 покрывает max
  tolerance8 + neighbour1 + feather2 + rounding2; old/new raster и dilation
  вычисляются с halo до crop, candidate меняется только внутри supplied ROI.

Финальная проверка:115tests PASS, включая real inline Qt pending contour→apply→
save→reopen PNG, RGB byte identity, Undo/Redo,9tolerance/feather circlecases,
отдельные pixels/holes, multiple draft paths/repeated edits, all-node full/local
15cases tolerance0.5/1/2/4/8×feather0/1/2, existing cancellation/editor/session.
Independent review latest37tests PASS +180tightROI probes; открытых confirmed
замечаний нет. Root повторил original repro:26/248/352 straypixels→0,1component.
4100px actual Qt fixture:apply0.252s, maxUI gap87.8ms, peakRSS593.8MiB на Linux.
Evidence: artifacts/contour-specks-verification в основном проекте.
Границы: synthetic/Qt offscreen, не installed Windows и не исходные PNG владельца.
Не включены новый инструмент лассо, global cleanup или упрощение интерфейса.




## studio3211-push-approval-block

Source commit9400729 создан после final2145tests+278subtests PASS, independent
review31tests PASS и sensitive scan PASS. Push отдельной ветки отклонён
автоматической проверкой разрешений: «отдельного явного разрешения именно на
push нет», требуется согласие на передачу кода во внешний GitHub-репозиторий.
Remote lana-info/Clipart-Generator совпадает с проектом, PRIVATE проверен через
GitHub API. Обход отказа не выполняется. Владельцу задан точный вопрос о push
этого коммита. Затем владелец явно разрешил push и продолжение сборки.
Повторный push9400729 SUCCESS, обхода отказа не было. Helper
PUBLIC/build/PRIVATE запущен после push; exact expected head9400729.
Результат: run36783850992 SUCCESS; finally вернулPRIVATE. Root и независимый
агент live GitHub проверкой подтвердилиPRIVATE. Скачанный installer3.2.11,
source9400729, SHA256 и provenance совпали; все13 installed frozen Corechecks PASS.
Evidence в artifacts/studio-3.2.11-review-candidate основного проекта.
Реальный customer-license download/open и upgrade3.1.4 не проверены;
соответствующий legacy fixture шаг SKIPPED. Серверная публикация не выполнялась.

## paid-history-eviction-before-studio3211

После разрешения владельца на commit/build residual hypothesis проверена.
Completed upscale запись вытесняется limited journal перед retry acceptedremover:
KIE/Fal red2FAILED/6PASS. Добавлен durable paid_completed_stages marker и
recovery_completed_stages, exact matching отсутствует → failclosed без POST.
Первый вариант маркера из localstage complete имел остаточную дыру:
provider success→localdownload failure оставлял localstagefailed без paid marker.
Independent repro вновь создал2POST. Причина пересмотрена до новой правки.
Маркер теперь захватывается индексированным provider_task_succeeded до download;
changed.emit checkpoint, local stage status не подменяется. Red2FAILED/14PASS,
после исправления24 worker tests PASS, independent standalone1POST и31tests PASS.
Повторный retry сохраняет marker; AutoClipart сохранение/открытие переносит его.
Optional field ограничен3known unique stage names; старые rows принимаются,
7invalid/duplicate field shapes rejected независимо reviewer.
При missing/evicted journal recovery блокируется, требует ручного решения;
не следует запускать платные этапы повторно скрытым fallback. Логи:
/tmp/review-history-eviction-red.log, /tmp/review-paid-download-confirmed-red.log,
/tmp/studio3211-paid-final.log. Final full source2145tests+278subtests PASS,57skipped/20deselected,275.65s;
лог /tmp/studio3211-final-full-pytest.log. Sensitive tracked scan PASS.

После возобновления поручения code version3.2.11, Azure default синхронизирован.
Все6 подписанных1.5.2 требуют3.2.11; official signature/runtime/Qt smoke PASS.
Public/private build helper prepared /tmp/studio-public-build-3211.py:
expected commit check,90min bound, SIGINT/SIGTERM, finally6attempts restore PRIVATE.
Сборка и серверная публикация пока не запускались на момент записи.

## studio-full-review-fixes-20260930

Все13 находок повторно подтверждены независимым read-only ревью на6ddedb1.
R1 offline cache переживает explicit validation denial; R2 provider journal
зависит от изменяемого локального индекса retry; R3 raw cleanup не согласован
с source_path очереди; R4 save-before-leave действует только для auto-clipart.
R5 DPI отсутствует в guard worker; R6 legacy generation/runtime не доходят
до workflow; R7 QC cache зависит только от paths/membership; R8 inventory
исторических версий ошибочно требует runtime compatibility; R9 clock-skew
проверяется по-разному. R10 red textured fur теряет70 opaque RGB/alpha pixels;
R11 selection cursor заменяется snapshot либо сохраняется после смены locks;
R12 profile lookup выполняется по неуникальному name; R13 in-place editor save
не уведомляет обработчик lineage. Проверки и текущие статусы ведутся в STATE.md.

Исходные безопасные repro сохранены в /tmp/review_generation_*.py,
/tmp/review_module_*.py, /tmp/test_state_review.py,
/tmp/review_processing_export_6ddedb1.py и /tmp/pinterest-composer-review-run/.
Исправления выполняются в отдельных worktrees от6ddedb1; commit/push/build
не выполняются. Ни production, ни пользовательские данные не используются.


История исправлений:

- R1/R8/R9: очистка offline cache после явного validate403, общий skew и
  inventory без runtime compatibility. Исходные regressions7 failed/5 passed;
  дополнительное ревью: memory cache при write failure и signed empty/inverted
  диапазоны3 failed. Добавлены latch и отдельная range validation;
  итог135 tests+41subtests PASS. Restart после успешной записи denial проверен;
  при недоступном storage межпроцессная инвалидизация не гарантируется.
- R2/R3: исходный provider-index отделён от локального retry-index; raw без
  published final не удаляется. Два real-worker red tests FAILED до исправления,
  после исправления PASS. Qt reopening переведён с fabricated raw на настоящую
  worker failure, исходный PNG/sidecar существует после сохранения/открытия.
  Дополнительный независимый repro Fal: subsets3→2→1 и одинаковые prompts
  продолжают3 исходных task, новых submit нет; successful .run удалён.
- R3, повторное ревью: raw recovery принудительно выбирал U2Net, хотя исходный
  method был chroma. Red assertion и actual pipeline подтвердили подмену.
  Сохранён исходный provider/model; per-item blue восстанавливается из sidecar
  несмотря на global green. Удаление override обнаружило publication-only
  regression: remove_bg=False и ноль stages отклонялись guard. Red real-worker
  export-failure test подтверждён; добавлен явный publish_recovered_source
  только recovery-запросу, без искусственного remover или DPI.
- R3, финальное ревью: обработчик local files не переносил generation intent
  на recovered final. Red3 failed/2 passed; scoped capture verified v2 source
  и rebind final stage после PNG publication. OSError/ValueError sidecar остаются
  предупреждением, paid image успешно опубликован.29 tests+28subtests PASS.
- R4/R6: общий save guard и runtime/generation preferences.22 signed-workflow
  regressions PASS; affected138 tests+28subtests PASS. Busy message сохранён
  согласно существующему UI contract. Тест миграции изолирует LOCALAPPDATA
  до import main; реальный config/данные владельца не трогает.
- R5/R7/R13: DPI включён в guard; QC/export cache учитывает file version и
  review issues; успешное in-place save передаёт изменение lineage. Три actual
  UI/worker/export tests FAILED на6ddedb1, затем3 PASS на fix branch. ZIP содержит
  выбранные отредактированные PNG; generated rough удаляется только после
  успешной opt-in cleanup, пользовательский исходник сохраняется.
- R11/R12: save selected variant сохраняет whole working draft/order/cursor;
  locks/mode/profile сбрасывают cursor; duplicate profile labels различимы.
  Первый narrow cursor restore давал3manual snapshots вместо2; cause confirmed,
  восстановлен whole working draft, сохранённое имя перенесено отдельно.
  Final Composer73 tests+2subtests PASS; root интегрированный subset47+2 PASS.
- R10 причина: matte недооценивает genuine warm source chroma, точный flood-run
  теряет непрерывность после другого оттенка/AA. Попытка1: recurring pigment
  marker того же subject убрал70 defects;104tests+28subtests PASS, но новый
  adversarial long fibre выявил9/13 ошибочно promoted alpha.6→1 samples.
  Причина пересмотрена: та же chroma может быть mixture другого opaque pigment
  и key за пределами local veto. Попытка2: bounded palette-level mixture veto,
  включая achromatic shading; rim/slit/fibre coverage.05/.6/.96 и disconnected
  object safeguards.290 tests+46subtests PASS; red RGB/alpha outliers70→0 уже
  precise_result,78 final pixels changed, zero newly opaque true-partial pixels.
  Другие5fur/4botanical/6golden outputs (legacy/opaque) побайтно неизменны.
 2048: baseline433.34MiB/4.138s, candidate427.15MiB/4.152s (<448MiB).
  Root inspected /tmp/chroma-red-fix/red-fur-before-after-crops.png;
  partial edge errors остаются, full real-image visual acceptance не заявлена.


- R2/R3, дополнительное независимое P1: accepted paid processing initial URL
  генерации и retry upload/dataURI имеют разные fingerprints. KIE и Fal
  real-worker red tests2 FAILED, затем PASS: известные URL/локальные bytes
  получают общий SHA256 alias, model/parameters/origin match остаётся обязательным.
  Reviewer выявил удержание полных Fal dataURI до завершения batch (10PNG256²:
 2,629,192chars). Добавлены компактные alias SHA256 самого dataURI; actual input
  digest вычисляется по сериализованным bytes без повторного чтения файла.
  Регрессия10randomPNG: keys всего<1000chars, полные dataURI не удерживаются.
- R2/R3, цепочка paid upscale→remover: timeout второго accepted stage приводил
  к повтору completed upscale и новому remover,4POST вместо2. Independent repro
  /tmp/review_worker_paid_processing_chain_retry.py. Добавлен alias скачанного
  upscale результата и recovery-only повторное получение completed journal task
  через существующий read-only polling. Failed/cancelled tasks не переиспользуются;
  генерация и обычный новый запуск не берут completed. Повторный fetch, если
  provider result уже недоступен, остаётся ошибкой без нового paid submit.
  KIE/Fal workers first-stage/second-stage timeout cases проходят с ровно1/2
  create calls и empty pending;11 worker regressions PASS. Параметры, model,
  changed source bytes и original index по-прежнему не допускают чужой task.
- Первый полный offline run:2124 PASS+278subtests,1FAIL в старой fixture уборки
  raw,57skip/20deselected. Она ожидала удалить genraw без published owner, что
  противоречит подтверждённой R3. Fixture теперь изображает реально completed
  owner {path,sha256}; проверка удаления своего run и сохранности чужого прежняя.
  Topaz routing fixture раньше вообще не писала fake download; теперь пишет
  dummyPNG во временную папку, прежние model/payload assertions сохранены.

Проверочные логи: /tmp/review-fix-*-red.log и *-green.log,
/tmp/review-root-final-focused.log, /tmp/review-fixes-provider-regressions.log,
/tmp/review-fixes-https.log. Повторное scoped ревью подтвердило остальные
worker/editor исправления; full independent review финального diff завершён: незакрытых подтверждённых
замечаний нет. Последний независимый subset78 tests+10subtests PASS;
root affected149 tests+21subtests PASS. Final offline PASS:2132 tests+278subtests,57 skipped,20 network/paid
deselected,273.10s. Лог /tmp/review-fixes-full-final-pytest.log.
Старая red-fur xfail удалена после устранения дефекта и обычной green регрессии.
Локальный HTTPS18tests PASS31.60s в /tmp/review-fixes-https.log.
AST19 changed Python files и git diff --check PASS. Исходный6ddedb1/ветка
codex/integrate-processing-3.2.10 не менялись, чужой :memory:.ses сохранён;
в fix-worktree после тестов появился отдельный untracked :memory:.ses,
к изменениям исходного кода не относится. Commit/push/build/publication не выполнялись.
Hypothesis: ограниченная completed history1000 может вытеснить раннюю задачу
очень длинной очереди до recovery; сценарий отдельно не воспроизведён.
Нативные Windows/actual license/live provider сценарии недоступны здесь.

## processing-3.2.10-integration, 2026-09-30

First integration suite: 2059 passed, one failure in release contract after
VERSION.txt advanced to 3.2.10 while Azure appVersion default stayed 3.2.9.
Cause verified in both files and test assertion; align Azure default to 3.2.10
and recheck release tests. Existing assertions are unchanged.

Signed-module smoke harness initially omitted the image-processing capability
broker and used command install instead of declared install_workflow. Inspected
runtime/module entry contracts, corrected harness only, then verified official
signed Processing/image-processing 1.5.1: install, activation, loaded Auto UI and
engine removal PASS. Both reject Core3.2.9 due to minimum3.2.10. No application
fix needed for these diagnostic mistakes.

Windows workflow36719207715 failed before any build step. GitHub annotation
confirmed an Actions budget block; no source-code change can fix it. No installer
artifact exists from that attempt. The owner authorized temporary PUBLIC
visibility, build and return to PRIVATE. Run36723401830 from00588a2 has now
started, confirming the budget block is avoided by the authorized route.
No billing change or application fix was needed. All six signed modules1.5.1
passed installation and runtime activation against integrated Core3.2.10.
Final run36723401830 SUCCESS; helper restored PRIVATE, independently confirmed
with GitHub API. Installer source/version/hash verified and installed report
contains13 successful checks. Budget blocker resolved for this build.
Additional package UI harness initially treated auto-clipart as ProjectMode;
the contract uses CLIPART mode with a separate workflow identifier. Corrected
only the harness; all five workflow pages, Processing provider/Auto UI,
Composer local variants and shared chroma smoke then PASS.

## Подготовительное ревью Studio 3.2, 2026-09-10

1. Сохранённая контурная копия оставалась только в редакторе, тогда как ZIP
   использовал прежний session.items.output_path. Добавлена передача пары
   исходник/копия контроллеру результатов; обновляются успешный результат и
   принадлежность набору. Копии вне output допустимы только после явного
   сохранения редактором. Integration проверяет настоящий модальный редактор,
   отмену, неизменность исходника, байты PNG в ZIP/PDF-пакете, повторное открытие,
   вторую копию, сохранение проекта и отказ от постороннего исходника.
2. Общий скан credential-полей считал пути в clipart.export_membership именами
   полей. Только этот словарь теперь проверяется по схеме назначений; проверка
   настоящих полей и вложенных значений сохраняется. Integration: create/save/
   restart/load для secret-garden и Windows Users/token; неверные и секретные
   поля не перезаписывают сохранённый проект.
3. При вытеснении snapshots Undo возвращался к первоначальной alpha вместо
   предшественника первого сохранённого изменения. Сохранена подвижная база
   истории с учётом памяти, Reset отдельно использует неизменяемый исходник.
   Проверены пошаговые Undo/Redo, лимиты числа/байтов, новый edit после Undo
   и Reset. Старое утверждение теста, закреплявшее перескок, исправлено.

Все три дефекта воспроизведены до изменения реализации. Проверки и статус
нового независимого ревью находятся в STATE.md.

## processing-background-choice, 2026-09-29

Симптом: Windows 3.2.8, вкладка Обработка, результаты трёх PNG теряли рамку,
голову гуся и ботву. Диагностика подтвердила local_rembg/u2net и только этапы
background_removal/export; все три ошибочных результата отмечены succeeded.
Причина отсутствия выбора: общий редактор принудительно скрывал существующие
provider/model/colour controls. Качество сегментации U2Net не исправляется
возвратом выбора; это отдельное ограничение. Автоподбор генерационного цвета
и загрузка его provenance уже существовали, автоопределения произвольного
импортированного PNG в Processing не было.

Исправление: включаем существующие controls только для Processing. Добавлен
режим auto с определением насыщенного RGB-фона по четырём краям (90% согласия,
основной канал >=150 и превосходство >=80). При неоднозначности сохраняется
исходник и требуется ручная проверка, без нейросетевого fallback. Подтверждённая
запись цвета генерации приоритетна. Default auto только для новых Processing
настроек/рецептов; старые явные цвета сохраняются. Выпадающие поля ограничены
240/360px, текущее название полностью доступно в tooltip.

Проверки: синтетическая смешанная RGB-партия через настоящий worker, сохранение
исходников, приоритет metadata, отказ для белого/серого/тёмного/смешанного фона,
UI-to-request/preflight, project roundtrip, условная видимость и Qt-снимки.
На 72.png, 50_goose_in_garden_arch.png и 42.png определён blue. Это проверка
детектора, а не новая визуальная приёмка полного удаления. Итог прогона в STATE.md.
Белый алгоритм не реализован; Windows-сборка/платные вызовы не запускались.

## Test-environment persistence regression observed, 2026-09-29

Полный прогон обнаружил семь падений UI-проверок сохранения настроек.
Ранее на исходной 3.2.8 повторно проверен только один из семи тестов, поэтому
утверждение, что все семь проверены на исходной версии, было слишком сильным.
Диагностика подтвердила общую причину: fixtures подменяли CONFIG_FILE/ENV_FILE,
но оставляли USER_DATA_DIR настоящим. ProtectedFalCredentialStore при сохранении
пустого ключа обращался к настоящему fal_api_key.bin; read-only filesystem
возвращал EROFS и сохранение config прекращалось. Это ошибка изоляции тестов,
а не основание отключать защиту ключей.

Причина → изменение → проверка → результат: неполная изоляция пользовательских
путей → семь fixtures одновременно подменяют CONFIG_FILE и USER_DATA_DIR
через patch.multiple → все семь файлов тестов плюс тесты credential store →
49 passed, 18 subtests, 1 expected Windows DPAPI skip. Assertions и production
credential handling сохранены. Итог повторного полного прогона в STATE.md.

## processing-review-followups, 2026-09-29

Независимый reviewer на gpt-6.1-sol подтвердил два пропуска:
1. При запуске автоматически создаваемый legacy config с local_realesrgan_dir
   проходил миграцию и заменял новый Auto на blue. Processing-only default при
   отсутствующем chroma_key_color теперь auto; явно сохранённые RGB-цвета и
   обычный генерационный blue остаются прежними. Регрессия проверяет миграцию,
   отсутствие мутации config и сохранение ручных цветов.
2. refresh_from_state блокирует сигналы combobox, поэтому смена рецепта оставляла
   tooltip предыдущей модели. Подсказка явно обновляется после refresh и после
   выбора профиля. Регрессия проверяет оба перехода на настоящем Qt-редакторе.

Проверки после исправлений: 80 passed + 33 subtests; reviewer follow-up
9 passed + 4 subtests. Повторный полный прогон с исправленными fixtures:
1985 passed, zero failures; финальные review-правки отдельно проверены после
того, как текущий полный прогон уже импортировал модули. Неизвестных новых
падений нет; известный red-fur xfail и платформенные skips сохранены.

## edge-separate-comparison-20261002

Новая offline диагностика a3f0b70 по согласию владельца «Давай» на сравнения,
без новой правки алгоритмов/интерфейса. Existing pale guard выключался только
в памяти в обоих импортирующих модулях и восстанавливался в finally. На13
402,126 RGB241,240,130→241,241,226sourceexact;376,129 RGB245,245,203→245,245,241.
Визуальное сравнение цветов использует одинаковую current alpha, намеренно
отделяя цвет от покрытия. Исходные solver alpha различаются14pixels, поэтому
эта фигура не заменяет полное сравнение результатов. Source foreground unknown.

Гипотеза: торчащие остатки можно убрать маленькими компонентами или alpha-only
opening. Изменение: только offline variants (≤2pixels/component, opening3×3),
RGB не меняется, не внедрено. Проверка:4real chroma PNG (включая saved14_ready),
2actual white-worker outputs,2syntheticsknowntruth,1genuine detached control.
Результат: components≤2 не существуют в4real и2white outputs; tiny rule ничего
не очищает. При knowntruth detached control удаляет2настоящие детали.
Opening удаляет338/233/385/393visiblepixels у13/07/14/14_ready,1289настоящих
furpixels (60opaque),602botanical (131opaque); заметно ослабляет усики бабочки.
В white outputs6/12pixels исчезают, но truth нет: не объявлять это улучшением.
Это риск предложенного эксперимента, а не новая внедрённая regression Studio.

Все4исходника провереныSHA до/после. Диагностические PNG сохранены/прочитаны
exact. Figure inspections обнаружили ошибку самой иллюстрации: первый crop
мишки попадал на фон, исправлен crop после обзора реального1536pxoutput;
zoom-detail label исправлен300→600% в соответствии с actual nearest scale6.
Эти изменения не затрагивали алгоритмы и повторную inference. Main просмотрел
итоговые изображения; ideal masks real/semantic edge colours неизвестны.
Evidence: ../artifacts/edge-comparison-20261002, /tmp/edge-comparison-20261002.log.
Исходники пользователя/приватные PNG не включать вGit; сервер/сборка неизменны.

## party-duck-5016-contour-quality

Actual uploaded utochka_v_prazdnichnom_01_ready.png:5016×5016RGBA,
6858110bytes,269424partialalpha,18198068zeroalpha. Main inspected dark composite
and original-scale ROI3190,1560,3530,1920: dark/purple-green edge stripes exist
in the savedPNG, not merely the attached screenshot. No original pre-cutout
or receipt metadata supplied, exact originating stage remains unknown.

Hypothesis for unavailable curves: current4100-side guard. Read-only actual
_calculate_contour('extract',alpha,(),(),Event()) reproduced ValueError:
«Автоконтур поддерживает до4100px по каждой стороне». _start_contour rejects
before starting. Separate core extract_contours raises too-many-contours:
903contours,568components atalpha>0,MAX_PATHS256. At>8:16components,29contours;
at>32:1component,5contours. These are diagnostics, not safe thresholds: applying
threshold can delete genuine semitransparent detail. Older standalone dialog
has separate4MP auto limit; installed version unknown. File25.16MP is below
current editor40MP and contour32MP total limits, PNG6.54MiB is not byte-size cause.
No limit lifted, mask thresholds applied, user file modified, source fixed,
model/API called or build started. Preserve full resolution for a future bounded
ROI/geometry solution rather than asking the user to downscale originals.
Evidence/private SHA and figures: ../artifacts/party-duck-diagnostics.

## large-contour-and-weak-paint-fix

User's standing implementation approval reaffirmed; work on dedicatedfixbranch.
Root cause1:5016px rejected by4100side guard despite supported32MP core budget.
Raw faint noise creates903contours/5256nodes. Fix: existing32MP total bound with
32768side guard; proposal extraction tries rawalpha first and only when geometry
budget is exceeded alpha>8 proposal. Full raster alpha is never binarized/deleted;
unchanged apply preserves bytes. Matching proposal ownership still flood-fills
raw8-connected source. Do not infer aggregate test totals from overlaps.

Review caught omitted faint4×4 island inside hole erased by outer shrink. Root:
polygon coverage != raw connected ownership. Regression narrow corner90,90→110,110,
hole92:108,island97:101alpha3 with many faint specks; prevent old_only removal
for non-owned visible pixels of trusted extracted exteriors.61independenttests
and48alpha1..8×feather0/1/2×exterior/hole probes PASS; outsideROI exact.
First focused Qt process segfaulted after10tests while fixtures recreated QApplication;
exact root cause unconfirmed. Holding one QApplication for the test process yields
85then188PASS with tests/guards unchanged. One broadened invocation named two
nonexistent test modules (exit4); corrected discovery, not production failure.
Actual5016Qt separate-save preserves sourceSHA/RGB/alpha/size/UndoRedo.
Global timer gap1.1s includes save/history steps: do not promise native smoothness.
Region refresh uses worker changed bounds, avoiding full-image recomposite on normal apply.

Root cause2 on knowntruth: source-painted(80,70,90) thin stroke gets treated as
weak blue mixture (83,72,83,244); later borrowed cream fit gives92,78,66,222.
First in-memory prototype restores precise step but fails2width cases later in
edge_mixture. New trace proves protection must survive later stages. Explicit
per-call sourcepaint mask: opaque_clipart/sourcealpha255/provisionalalpha242..254,
weakkeydominance≤24/flat source tangent run/nearest eroded opaque core≤12px;
convex fixed-colour fit residual>5 means unsupported borrowed-material correction.
Carry sourceRGBA for admitted pixels through all later fits; no module-global mask.
9new key×width cases at every observer stage PASS, existing187tests PASS, production
196focused PASS,52contracts+12subtests PASS.6weak.95/.98 compatibility controls do
not certify ideal alpha;2sourcepartial +threaded cases protect non-promotion/state.
Identical(80,70,90) may be a true opaque additive mixture; the agreed ambiguity
policy preserves source paint and can leave weak additive spill. No claim of
perfect recovery or real duck stripe origin. Profilev11; existingv10 receipts
remain original and readable. Frozen packages/builds/server untouched.
Evidence:/tmp/duck-weak-paint-guard-carry-probe.py,/tmp/weak-material-production-first.log,
/tmp/weak-material-contracts.log,../artifacts/party-duck-contour-fixed.


## party-duck-upscale-alpha-ringing

Владелец прислал rough_05_generated RGB1254², rough_08_bg-removed RGBA1254²
и rough_01_upscaled-after RGBA5016². SHA originals сохранены. Весь visible RGB
готового файла совпадает с upscaledafter, значит последний contour/save не
перекрашивал эти пиксели. Alpha upscaledafter byte-exact равна исходной alpha,
увеличенной Lanczos. 569 отдельных alpha-positive components появляются в ней;
при bilinear на том же источнике 1 connected component. Это подтверждает
ringing восстановления маски, но не доказывает, что вся тёмная краска искусственная.

Также _run_local_realesrgan передавал neural model source_rgba.convert('RGB'),
включая скрытый синий key под alpha0. Hypothesis о влиянии синего на восстановленный
RGB подтверждается входом операции, но реальный Windows model rerun пока недоступен.
Исправление: extend nearest opaque foreground только под alpha0 во временном RGB;
когда opaque нет, nearest positive alpha; visible pixels byte-exact.
Мягкая alpha теперь bilinear без отрицательных lobes, hard alpha nearest сохранена.
Не threshold/delete/erode весь пух. Исходные файлы и сохранённые готовые PNG не меняются.

Две регрессии до правки FAILED: input alpha0 оставался keyblue; restored alpha
содержала detached lobes. После первой правки обе и straight-soft-RGB test PASS
(3tests0.96s). Добавлены empty/opaque/soft-only и hard-mask controls, итоговый
прогон и independent review завершены:6tests+3subtests и70controls PASS.
RGB preparation теперь внутри try/finally; injected failure подтверждает cleanup. Private real comparison:
../artifacts/party-duck-alpha-upscale-fixed/verification.json и alpha-only-edge-comparison.png.
Числа569→1 относятся только к той же alpha, не к запуску neural upscaler.
Neural RGB старого файла сохранены в сравнении намеренно: полосы, уже встроенные
в RGB, нельзя честно объявлять устранёнными этим mask-only результатом.


## auto-clipart-count-recoverable-export-20261002

Подтверждено20→1 оставляло20objects/jobs и19missing блокировали ZIP1ready.
Причины: fill_recipe только рос, snapshot возвращал старые counts; Back сбрасывал
session, restore CANCELLED→FAILED; export issues учитывали inactive recipe objects.
Исправлено exact active/inactive count, previous_runs paid history, Back без reset,
CANCELLED сохраняется; export учитывает actual requested IDs. Reuse требует exact
prompt/settings fingerprint и валидный output path. Legacy unknown FP не выдумывается.

Независимое review выявило mixed valid-ready+missing-paid случай: пустой FAILED
record терял source/paid evidence. Valid-ready включал reuse всей session.
Новые данные воспроизведены; deepcopy старого record до смены status/message
сохраняет evidence. Regression: missing paid source preview_retry None/factory0.
После reuse1ready+19never-submitted retry выбирал только FAILED. Shared retry_indices
включает CANCELLED, explicit confirmation и paid-stage/source guards сохранены.
Ready1 исключён; decline не меняет statuses/attempts/evidence, provider0.
123tests+9subtests PASS100.08s, independent28targeted и processing/Pinterest probes PASS.

Владелец одобрил table/ready/issues/empty mockup2026-10-02. Таблица основной страницы,
immediate checkbox persistence, English defaults/custom names intact. Explicit
ready-only bypass только missing, не ambiguity/invalidPNG. Незавершённые records
сохраняются, reopen сбрасывает partial consent. Footer ZIP+authoritative Save project;
save error не показывает успех. Actual legacy20items/1ready/19failed→select→save→ZIP
CRC/PNG exact→reopen selection/19failed intact, no provider.41UI+5subtests,
7planner+5subtests и2actual integrations PASS. Independent49tests+10subtests и
actual partial/save error/retry/freeze probes PASS; новых дефектов нет.
Actual1120×780 footer reachable; safe-dummy approval/actual artifacts:
docs/ui/3.1/export-table-20261002/.

Первый общий прогон прерван после новых owner PNG для необходимого upscale fix;
exit130 не является успешной проверкой. Финальный полный suite выполняется отдельно.


Финальная root-проверка таблицы обнаружила ещё один воспроизводимый дефект:
оба варианта включены→снять второй→включить обратно. Resolver необратимо удалял
resolved ambiguous из единственного inventory, и повторное включение не блокировало
экспорт. Независимое review воспроизвело то же, _export открывал picker.
Новые данные подтвердили причину; теперь отдельный исходный candidate inventory,
current blockers пересчитываются при каждом изменении. Regression baseline FAIL,
после fix проверяет repeated toggle/zeroactive/partial и отсутствие picker.

Общий pytest через stdin завис на multiprocessing spawn в chroma benchmark;
faulthandler показал popen_spawn_posix._launch/process.start, не UI operation.
Два таких прогона прерваны exit130 и не считаются PASS. Guarded временный
file runner сохраняет одну QApplication и не запускает pytest в spawn child;
те же19benchmark tests+6subtests PASS8.83s без изменения тестов/продукта.
Финальный общий suite выполняется через этот file runner.

Независимое повторное review того же inventory обнаружило отдельный reopen false-block:
сохранённый выбор одного варианта отображался, но новый dialog не пересчитывал
исходный ambiguous до первого interaction. Root baseline regression FAIL подтвердил
условие. Constructor теперь resolver(saved_membership) перед первым summary refresh;
новая regression требует reopen enabled и reselect blocked. Вынужденный общий
file-run прерван до этой source правки; окончательный run начинается после неё.

После обоих ambiguity исправлений:46target UI/planner/integration tests+5subtests
PASS5.68s. Финальное независимое review52tests+10subtests PASS2.43s,50toggle/reopen
cycles PASS; новых подтверждённых дефектов нет. Full source теперь неизменен.


Финальный file-run общего safe suite:2481passed,1failed,57skipped,21deselected,
281subtests PASS419.47s. Единственный failure exact architecture inventory:
studio_auto_clipart_state→studio_clipart_objects. Причина: новая combined inactive
schema validation использует существующий pure validate_objects, пара отсутствовала
в reviewed baseline. Независимо подтверждено module-owned extension подключение,
validation не импортирует flow/UI и не запускает jobs. Добавлена ровно эта пара
с объяснением; строгий added/removed comparison и запрет wildcard не ослаблены.
26dependency/inactive/history checks PASS2.73s; independent26PASS2.68s.
Production sources после full-run не менялись; полный suite повторно не запускался.
57skips:3native contracts (DPAPI, Windows sharing, отсутствующий RealESRGAN) и54
отложенных six-slot Pinterest;21network/paid deselected. Pillow getdata deprecation
в новой test-only regression зарегистрирован как warning, не дефект продукта.
