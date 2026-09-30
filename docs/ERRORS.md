# Ошибки проекта

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
