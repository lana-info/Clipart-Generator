## Апскейл: тёмная кайма по краю светлых клипартов, 2026-10-22 {#upscale-dark-edge-halo-20261022}

Симптом (тест владельца, пчела с кремовыми крыльями): на светлом или белом фоне
по краю готового PNG идёт тонкая тёмно-серая полоска; на тёмных клипартах не видна.

Причина: исходник нейросети уже с прозрачным фоном, но под прозрачностью лежит RGB 0,0,0,
а по самой кромке (alpha 1–2) почти невидимые пиксели с чёрным/белым цветом. В Real-ESRGAN
уходит только RGB (`_run_local_realesrgan`), поэтому нейросеть апскейла видит чёрный
фон и добавляет тёмные пиксели на границе. Мера «край темнее внутренней части»:
исходник 1254 px — 1,8 из 255, финальный файл 2000 px — 11,2. Ранее
`_prepare_upscale_rgb` перекрашивал только alpha==0; на проверочном растягивании это
почти не меняло результат (5,2 против 5,1 с чёрным), т.к. мусорная кромка с alpha 1–254 оставалась.
Хромакей и Unsharp не виноваты (Unsharp: 1,5).

Решение: `_prepare_upscale_rgb` перекрашивает также мягкую кромку (alpha<255 в пределах
`UPSCALE_ALPHA_RIM_PIXELS`=3 px от alpha==0) цветом ближайшего непрозрачного пикселя.
Alpha берётся из исходника, форма края не меняется. Прежний тест на сохранение
цвета полупрозрачного пикселя обновлён под новый контракт.

Проверка: новый тест `test_upscale_rgb_replaces_dark_junk_in_soft_alpha_rim` падает на старом
коде и проходит на новом; tests/test_local_processing_acceptance.py, test_chroma_nn_working_alpha.py,
test_upscale_positions.py, test_windows_realesrgan_bundle.py — 87 passed, 1 skipped.
Саму Real-ESRGAN не запускали (нет бинарника/модели в среде): эффект подтверждён симуляцией
Lanczos и только на синтетике/одном файле. Нужна проверка на реальной пчеле в сборке.
Не проверены апскейл через KIE/fal: у них вход с alpha, та же проблема возможна.

## Auto Clipart: имена файлов транслитерировались вместо перевода, 2026-10-22 {#autoclipart-filenames-translit-20261022}

Симптом (тест владельца): готовые файлы Auto Clipart названы латиницей по звучанию
(`gusenok_...`), а нужен английский перевод — продукт для англоязычных покупателей.

Причина: `output_naming._translate_common_subject` знает ~10 русских слов
(лиса, мишка…), всё остальное шло в `_CYRILLIC_TRANSLITERATION`. Имя строится
синхронно из «Объект: …» в `reserve_generated` (main.py, `_mode1_generate_parallel`),
переводчик из ручного экспорта (`studio_name_translation`) там не использовался.

Решение: `WorkerThread._english_file_subjects` один раз переводит уникальные
русские объекты одним запросом выбранной текстовой модели; результат передаётся
в `reserve_generated(..., english_subjects)`. Нет ключа/сбой — прежнее поведение
(словарь → транслитерация), запуск не блокируется. Ребро main → studio_name_translation
добавлено в allowlist архитектурного теста с пояснением.

Проверка: tests/test_output_naming.py, tests/test_autoclipart_english_file_names.py,
test_studio_dependency_architecture.py, test_export_names_translation.py — проходят.
Живой запрос к текстовой модели не выполнялся.

## Auto Clipart: один сбой файла останавливал весь пакет, 2026-10-22 {#autoclipart-one-failure-stops-batch-20261022}

Сценарий владельца (диагностика 3.2.38, воспроизведено дважды): пакет из 50
файлов, piapi/gpt-image-2.5; файл 27 — «не удалось завершить обработку файла»,
остальные не обработаны. По журналу: item_failed (27, provider_task_failed от
piapi, «An error occurred while processing your request…»), затем item_cancelled
для файла 24, работавшего параллельно, run_cancelled с 25 готовых / 1 ошибка /
24 отменены. Файл 26, уже запущенный, дошёл до конца; новые не стартовали.

Установлено (код): `WorkerThread._execute_item_entry` и опрос задачи
`_gpt25_generate_image` вызывали `request_stop_after_current()` при ЛЮБОЙ
ошибке piapi/atlascloud (защита платного пакета из 3.2.28). Воркеры очереди
перестают брать новые файлы, `_ensure_provider_submission_allowed` отменяет
идущие. Не установлено: почему piapi вернул ошибку (внешний сбой сервиса, на
нашей стороне запрос не проверялся; платные запросы для проверки не делались).

Отдельные дефекты, найденные при разборе:
1. `_autosave` (studio_auto_clipart_flow.py): после освобождения workflow
   capability таймер на 800 мс бросал `RuntimeError: Workflow capability is
   unavailable` на каждом тике (169 unhandled_exception в двух сессиях без
   запуска, 108 за ~90 с). На пакет не влиял. Почему capability исчезла при
   открытом мастере — не установлено; симптом закрыт остановкой таймера.
2. `RunQueueSession.handle_finished` писал `run_failed reason=missing_completion`
   даже когда не хватало ничего — были просто файлы в ошибке. Теперь
   `item_failures`; `missing_completion` — только при незавершённых файлах.

Неверные попытки/версии: считать причиной сам текст ошибки («не удалось
завершить обработку») — это обобщённая подпись `_failure_reason`, а не причина.
Решение: константа `PROVIDER_FAILURE_STOP_THRESHOLD = 3` (main.py); ошибка
файла помечает только его, успех сбрасывает счётчик; на 3-й подряд ошибке
провайдера — остановка после текущих и сообщение с объяснением и просьбой
повторить запуск (готовые файлы сохраняются). Подсчёт на стороне слота
провайдера сохраняет инвариант «приём закрыт до освобождения слота» (один
подсчёт на файл). Проверка: tests/test_auto_clipart_skip_failed_file.py (9
тестов: одиночная ошибка, серия с успехами, 3 подряд, не-провайдерские ошибки,
отсутствие двойного счёта, статусы failed/cancelled/succeeded и их
сохранение через normalize_state, причина run_failed, остановка таймера);
test_piapi_safe_batch обновлён под порог. Живой платный запуск не делался.

## Fal.ai upscale data-URI rejection, 2026-10-17 {#fal-upscale-data-uri-20261017}

Платный запуск владельца 17.10 21:44 UTC: этап upscale_after, provider fal,
модель bria/increase-resolution — HTTP 422 «Could not fetch image_url: URL
scheme 'data' is not allowed». Причина: `_fal_source_url` не имел HTTPS-пути и
передавал локальный PNG как data URI; страница модели не гарантирует приём
data URI. Исправление 3.2.30 (5131105): `FalClient.upload_storage_file` грузит
PNG в хранилище Fal (rest.fal.ai/storage/upload/initiate → presigned PUT) и
передаёт HTTPS URL; утечки ключа в PUT нет; при неудаче загрузки платный POST
не создаётся (шлюз before_paid_submit не задействован). 4 офлайн-теста
(test_fal_provider) PASS; живой повтор владельцем не выполнялся.

## Автосброс подтверждения запуска автосейвом, 2026-10-18 {#autoclipart-confirmation-autosave-20261018}

Сценарий владельца: ошибка генерации, затем повторный переход к результатам —
«Results can only follow an explicit review and run» (v3_wizard.py:722), дважды
связан с висевшим процессом ~50% CPU. Причина подтверждена кодом и отловлена
текстом: таймер автосохранения шёл в момент подтверждения запуска и сбрасывал
_run_request_key до входа в navigate. Исправление 3.2.29 (58a31a2): автосейв
останавливается на время подтверждения и возобновляется после; 4 регрессионных
теста + существующие worker-тесты PASS; владелец обновился и подтвердил работу.
Зависание CPU как причина НЕ установлено и не закрыто: см. STATE «Зависшие
процессы...», наблюдение владельца 2026-10-19 — после 3.2.29 не повторяется.

## Desktop CI3.2.24 byte-baseline mismatch, 2026-10-13

Run38504974478 наa5f60b1:1FAIL/3418PASS/57SKIP/21deselected/331subtests.
Отказ: test_chroma_material_causality legacy-blue SHA77eef4... →cfa8c2...;
chroma source/test файлы не изменены относительноdevelop/3.2 и3.2.23.
CI ставит незакреплённые requirements и получил NumPy2.5.4/OpenCV5.0.0.93/
Pillow12.3.0, тогда как native builds ставят constraints-build
NumPy2.2.6/OpenCV4.12.0.88/Pillow11.3.0. Локальный causal suite30PASS с
NumPy2.5.3/OpenCV5/Pillow12.3; изолированная замена толькоNumPy на2.5.4
тоже30PASS, поэтому одна версияNumPy не установлена как причина.

Перед правкой: подтверждено различие полного CI/native dependency stack;
точная численная операция, зависящая от среды, пока не установлена.
Попытка1: привести DesktopCI к уже согласованным native build constraints
без изменения golden SHA и тестов → полный CI на том же application payload.
Результат: run38505749323 на4927b37SUCCESS,3419tests/331subtestsPASS,
57SKIP/21deselected342.15s; golden test неизменен. Это подтверждает работу
согласованного dependency stack, но не локализует отдельную численнуюоперацию. Native installers не
пересобираются ради CI/docs: идентичность application payload проверяетсяgitdiff.

## PiAPI Cloudflare blocks Python User-Agent, 2026-10-13 {#piapi-cloudflare-user-agent-20261013}

Studio3.2.23 Windows11: свежий экспорт591events содержит последний пакет50images:
49provider_task_failed имеютHTTP403 дляpiapi/gpt-image-2.5-flare, ещё1item_failed
защищён старымunconfirmed marker. Новых submit/poll/succeeded нет. Повторное
сохранение ключа и бесплатная проверка баланса не помогли.403сам по себе не
доказывает неверный ключ; раньше приложение показывало только общую классификацию.

Причина подтверждена безопасным GET /account/info без ключа: стандартный
urllib User-Agent получает403 JSON с error_code1010,
error_name=browser_signature_banned, owner_action_required=true,
сообщением о блокировке browser signature. То же соединение с
VibixStudio/3.2.23 и Mozilla/5.0 получает401 Invalid API key.
Существующий APP_USER_AGENT="VibixImages/1.0 (+PyQt6)" получает401 как на
/account/info, так и GET /api/v1/task/vibix_readonly_probe_nonexistent.
Никакие реальные ключи, платные POST или существующие taskID не использовались.
Это подтверждает блокировку транспортного клиента на проверочной машине,
но ещё не подтверждает действительность ключа владельца или его IP/права.

Попытка1: отсутствующий явный UA в gpt25_provider.request_headers и
provider_balance.check_provider_balance → добавить существующий APP_USER_AGENT
только для PiAPI → регрессии worker POST/GET и actual balance transport сначала
2FAIL/13PASS, после правки весь профиль31PASS; GETс APP_USER_AGENT достигает401.
Multipart edit regression проверяет UAи на POSTс3локальными референсами, и наpoll.
Защита от повторной оплаты, ключевые headers и redirect guard не изменены.
Дополнительный live GET через исправленные request_headers/secure_json_request
с заведомо фиктивным ключом: poll401, JSON Failed to verify api key; Cloudflare1010
отсутствует. Исправленный check_provider_balance также достигает проверки
фиктивного ключа. Эти запросы не подтверждают баланс владельца.
Новых зависимостей нет. Сборка/публикация и платная Windows приёмка не проводились.

Дополнительная сверка официальной страницы GPT-image API в этой сессии:
https://piapi.ai/docs/gpt-image/gpt-image-api явно описывает gpt-image-2.5без
суффикса; прежнее утверждение об отсутствии модели в docs устарело.

## api-settings-review-9074a1c

Независимое ревью трёх коммитов cf9bb95, 99eb03e, 9074a1c обнаружило:

- P1: api_concurrency сохранялся в Core preferences, но
  enrich_image_worker_settings копировал только строковые поля. Общий шлюз
  запускал модули с прежним default3 вместо выбранных1/5; старые индивидуальные
  лимиты также не передавались. Реальные gateway/WorkerThread probes подтвердили
  api_concurrency=None и effective_limit=3 при обоих значениях.
- P2: AtlasCloud/PiAPI balance GET выполнялся в UI-потоке. При задержанном ответе
  Qt timer не срабатывал до возврата функции, окно не обрабатывало события.

До исправления: regression suite11FAIL/2PASS5.09s, лог
/tmp/vibix-api-fixes-red.log. Существовавшие558tests/70subtestsPASS не покрывали
эти сквозные сценарии;54отложенных Pinterest casesSKIP.

Попытка1: подтверждённые причины → нормализованные общий/legacy лимиты
передаются из Core с приоритетом над старым планом; два новых balance GET
вынесены в QThreadPool, результат доставляется queued signal в UI. Один запрос
одновременно, ключ очищается в worker, исключения не раскрывают его. Уничтожение
диалога автоматически отключает Qt slot, задача завершается в application pool.
Проверка → реальные исполнители генерации/обработки для1–5, legacy limits,
event-loop responsiveness, повторный клик, уничтожение окна и error redaction.
Результат →57PASS1.28s, /tmp/vibix-api-fixes-focused.log.

Расширенная проверка обнаружила новую архитектурную зависимость
v3_image_worker_settings(shared_api) → runtime_settings(Core):1FAIL1.70s,
/tmp/vibix-api-fixes-architecture.log. Причина: нормализаторы были импортированы
в общий слой. Коррекция по этим данным: общий слой только передаёт лимиты,
нормализация остаётся в существующем WorkerThread; legacy alias получает
приоритет Core. Allowlist и исходное архитектурное требование не менялись.
Проверка исправления границы вместе с новыми регрессиями:33PASS4.40s,
/tmp/vibix-api-fixes-boundary.log, включая save/reopen settings1/5.

Смешанный порядок mode-selection/composer → gpt25_recovery вызвал Qt
double free/corruption в существующем test_real_qt_cancel_button_preserves_expired_receipt.
Минимальный набор new-regressions+recovery:56PASS3.72s; расширенный порядок
воспроизвёл SIGABRT. Проверка удержания QApplication не помогла и удалена.
Тот же старый порядок без новых тестов тоже SIGABRT. Контроль с исходными
v3_api_settings/v3_image_worker_settings из9074a1c, загруженными из/tmp без правок
рабочей папки, воспроизвёл тот же SIGABRT: /tmp/vibix-api-fixes-qt-baseline.log.
Это прежний зависимый от порядка native Qt сбой тестов; точная причина
double-free пока не установлена. Production recovery не менялся, тесты не
ослаблялись. Отдельный порядок recovery → новые регрессии → UI:
177tests/30subtestsPASS31.44s, /tmp/vibix-api-fixes-qt-final.log.

Общий офлайн-набор на окончательных исходниках:3413tests/331subtestsPASS,
57SKIP,21network/paid deselected,4прежних Pillow warnings,501.26s.
Лог:/tmp/vibix-api-fixes-full.log, Python3.11.15/Qt6.11.0 Linux offscreen.
Полный порядок прошёл в том числе исходный Qt recovery case. Архитектурный
allowlist не менялся. Syntax, sensitive-artifact guard, diff-check и реальный
offscreen startup приложения PASS. Source-review финальных двухproduction diff
не выявил новых подтверждённых проблем. Из15новых регрессионных случаев10
измеряют реальные исполнители,2проверяют save/reopen,1legacy и2balance lifecycle.
Сеть и платные запросы в тестах заменены фиктивными ответами, production ключи
не читались. Windows и настоящие provider responses отдельно не проверены.

## stable-promotion-checks-20261012

Первый promotion-test command не собрал tests: source-пакетlicense_service
не был в PYTHONPATH существующего venv. Добавлен только актуальный service/src
в env команды; зависимости и production source не менялись. Повтор:2PASS0.84s,
1SKIP требует disposable PostgreSQL URL,45deselected. Рабочая штатная PG-операция
проверена preflight/backup/channel-only invariant и после неё14SHA/discovery PASS.
Текущий результат и ограничения: STATE.md; source artifacts и beta история сохранены.

## release-final-verification-20261012

После portable-doc fix full CI38200009717 SUCCESS:
3379tests+303subtests PASS326.30s,57SKIP,21network deselected,4Pillow warnings.
Native Windows/Mac ARM run38198534059 SUCCESS; frozen/extracted evidence PASS.
Published14beta rows, previous14withdrawn без удаления, new/oldSHA/fingerprints,
health200/token403/PRIVATE PASS. Текущий статус и ограничения только в STATE.md.

## release-portable-doc-links-20261012

Final Desktop CI38199191490:3378PASS+303subtests,1FAIL338.24s.
test_local_markdown_links_resolve нашёл3ссылки в старой записи docs/ERRORS.md
на sibling artifacts VDS. Локально эти файлы существуют, в GitHub checkout их нет.
Ссылки заменены явными локальными путями без неработающей Markdown-навигации;
доказательства не удалены и тест не изменён. Проверка tracked-file layout в
изолированном каталоге без sibling artifacts PASS;4documentation tests PASS0.17s.

Дополнительная HTTPS-доставка: первый запуск не стартовал18fixtures из-за
отсутствующего psycopg в UI-venv. Выбран существующий license-entitlements venv,
зависимости не добавлялись. Старый release-catalog service затем дал12FAIL/6PASS:
он не имеет shared image-processing entitlement bridge. Код подтвердил прямую
проверку module_id вместо allows_release_package. Актуальный coming-soon service
имеет bridge: тот же набор18HTTPS tests PASS32.63s, временные ключи/лицензии,
production business-data не менялись. Fixture создал :memory:.ses в checkout;
файл mode0600 сохранён в /tmp/clipart-delivery-fixture-20261012 вне source.
Path.rename между mounts дал EXDEV; shutil.move сохранил файл без вывода содержимого.

## release-contour-brush-control-20261012

Полный offline suite:1182PASS+95subtests,1FAIL,1native Windows SKIP250.72s.
Ошибка hardness_slider воспроизведена на исходном fd46e5a (1FAIL0.69s).
Текущий UI выбирает Жёсткая/Мягкая через brush_style_buttons; slider удалён.
Тест переключает настоящую кнопку Жёсткая и проверяет hardness100, сохраняя
проверки stroke, preview, undo/redo и применения контура. Production-код не менялся.
Focused contour/release:26tests+4subtests PASS3.56s. Повтор полного suite в работе.

Второй full suite:3378PASS+303subtests,1FAIL,57SKIP,21network deselected493.33s.
Единственный remaining test_studio_contour_integration обращался к тому же
удалённому hardness_slider. На fd46e5a:13PASS+6subtests/1FAIL1.94s.
Исправлен выбор реальной Жёсткой кисти через QTest; проверка3px footprint сохранена.
Contour/transparency после исправления:54tests+6subtests PASS6.48s.
Первый focused command содержал неверный test_transparency_preview.py, тесты не
запускались; после rg --files выбран существующий test_v3_transparency_preview.py.
Runtime-проверка подписанных модулей сначала использовала fixture без права
auto-clipart и получила ожидаемый authorization deny. Добавлено только тестовое
право; actual4workflow opens и image-processing на2profiles PASS, 0 paid jobs.

## release-acceptance-resume-20261011

Полный offline suite перед выпуском обнаружил устаревший
acceptance test_home_refreshes_rights_and_keeps_saved_project:
AttributeError saved_project_buttons. Дефект теста воспроизведён отдельно на
исходном fd46e5a, до recovery/version изменений (1FAIL2.30s).
PROJECT.md требует одно меню «Продолжить работу» вместо карточек; текущий
ModeSelectionScreen уже использует all_projects_button/QMenu.
Изменение: тест выбирает сохранённый проект через реальное действие меню,
проверяет точный project_id, восстановление имени и отсутствие worker.
Production UI не меняется, сохранение и reopening продолжают проверяться.
Обновлённый сценарий PASS в focused release suite (36PASS до следующего сбоя).
Исходный full suite остановлен после найденного сбоя; повтор полного набора
предстоит после проверок версий.

## release-version-consistency-20261012

Focused release suite: 36PASS, 1FAIL11.73s. test_azure_default_matches_release_version
обнаружил default3.2.18 в azure-pipelines.yml при новом release/VERSION.txt3.2.21.
Причина: смена версии должна согласованно менять обе release-конфигурации.
Исправлен только default до3.2.21; проверка исходного контракта без изменений.
Повтор release contracts: 46tests+4subtests PASS10.97s. Полный offline suite в работе.

## gpt25-recovery-20261011

Ревью fd46e5a: три воспроизводимых дефекта восстановления.
1. Сохранение accepted task_id и завершение unconfirmed-маркера двумя записями:
   прерывание второй записи оставляет submitting раньше queued; повтор блокируется.
2. Отмена после сохранения submitting, но до сети попадает в общий except:
   неоплаченный запуск становится «неизвестным» и блокирует повтор (0 HTTP opens).
3. Любой отказ GET становится poll_deferred: удалённая задача PiAPI (HTTP404)
   опрашивается при каждом новом запуске. Документация PiAPI хранит async-результат
   60 минут: https://piapi.ai/docs/gpt-image/gpt-image-api.

Исходные воспроизведения: /tmp/clipart-review-fd46e5a-2na22m9z/review_probes.py.
Решение:
- accept_submission заменяет submitting-маркер принятой queued-задачей одним
  atomic replace под существующими thread/process locks. Известные receipts
  старых split-журналов восстанавливаются безопасным GET; неизвестные отправки
  не снимаются автоматически, чтобы не допустить повторной оплаты.
- Transport выставляет gpt25_post_started только непосредственно перед open.
  Отмена до этого момента завершает маркер как cancelled; отмена/потеря ответа
  после начала отправки сохраняет guard. Paid POST не ретраится.
- HTTP404/410 сохраняет expired; следующий запуск не делает GET/POST без
  отдельного согласия на новую оплату. Core и legacy окно используют общий
  QMessageBox с default No и родителем активного окна. Согласие связано с ID
  задачи и точными project/item/model/payload scopes; Core удаляет согласие из
  пользовательского плана до проверки. Новый receipt и superseded-история
  сохраняются атомарно. Временные/authorization ошибки остаются poll_deferred.

Проверки:
- До реализации:11 регрессионных checks FAILED на исходном fd46e5a,
  подтверждая дефекты и отсутствие атомарного принятия.
- Первая реализация:33tests+5subtests PASS. При проверке diff исправлен вызов
  отсутствующего helper в legacy-обработчике ошибок; добавлена проверка этого UI.
  Уточнена совместимость старого unindexed generation receipt; отдельный test PASS.
- После расширения:41 recovery checks PASS1.95s. Реальные transport/journal/worker,
  прерывание до/после atomic replace и POST, HTTP403/429/500/504 без повторных POST,
  HTTP404/410, consent Yes/No, forged saved consent, scopes, all5 final PNG routes,
  legacy/Core UI и реальный Qt-клик No.
- Итоговая интеграция:548tests+35subtests PASS37.82s;1 native Windows DPAPI SKIP.
  Git diff --check и py_compile PASS. Платных/live запросов0; сборка/native
  Windows/macOS и публикация не выполнялись. Итоговое состояние: STATE.md.

# Ошибки проекта

## chroma-material-mode-20261005

Full-suite2770PASS/2failure: test_auto_chroma_detects_each_file... предполагал приоритет generation record над auto, а test_processing_page_exposes_every... предполагал отдельный UI для каждого dataclass field. Это противоречит утверждённым actual-auto и внутреннему override. Новые ожидания проверяют actual color/RGBA/source preservation несмотря на другую declared key, а completeness исключает только невидимый compatibility flag. Production-код ради этих проверок не менялся. Контрольный affected-suite194PASS/1skip/9subtests; final readonly review0findings.

Причина исходного расхождения мишки: ProcessingEngine.remove жёстко передавал opaque_clipart, а принятый серверный PNG получен legacy. Новый optional профиль в API1, объявление поддерживаемых режимов engine и сохранение настройки → real Worker pipeline на3 синих исходниках →0RGBA различий у каждого, включая мишку. Белый фон не исправляется:3 white sources получили manual_transparency_required, originals unchanged.

Ревью оппонента выявило constructor AttributeError: проверка совместимости обращалась к remove_bg_provider до присваивания. Перенос после initialization → существующий component integration и новые worker tests →PASS. New roundtrip test выявил существующий _sync bug: recipe='custom' записывался и в ClipartModeData.recipe dict|None. Ограничение assignment случаями str → mode change/save/reopen →PASS, Processing recipe semantics сохранены.

Дополнительное ревью подтвердило, что manual GUI color проигрывал per-entry/record. Persisted chroma_key_color_override=False и activated-only callback, override после прежней проверки record → новое15-case suitePASS, generation record unchanged. Нулевые default-ключи исключены из worker settings для сохранения старых fingerprints. Старый компонент поддерживает opaque, а legacy отклоняется до запуска Worker и платной генерации; metadata новых пакетов блокирует Core<3.2.12.

Два первоначальных pytest command ссылались на несуществующие файлы и не запускали тесты. После rg --files команды составлены по существующим тестам. Первое выполнение связанных проверок:2failures (constructor bug и устаревшее ожидание скрытия активной rembg-модели). Constructor исправлен; UI tests обновлены по утверждённому показу метода, проверки скрытия неактивных полей сохранены. Provider registry old tuple ожидал1 поле; обновлён на2 по новой спецификации. Итоговый targeted suite167PASS+5subtests, new tests15PASS.

Офлайн-стенд check_real.py сохранил все6 результатов, но финальный SHA assertion упал: helper ожидал Path, а JSON keys имели str. Original script/parameters/results сохранены. Отдельный finish_verification.py повторно проверил PNG byte comparisons и12SHA без повторной обработки:PASS. Это ошибка проверочного стенда, не конвейера приложения.


## remaining-edge-20261003

### Причины цветной каймы: сводка доказательств и гипотез

Текущий вывод: кайма возникает по нескольким причинам. Исправление одного
этапа не гарантирует, что следующий этап не создаст другой оттенок. Задача
устранения всей каймы не завершена; новые кандидаты ниже не внедрены.

**Подтверждённые механизмы**

1. **Заимствование цвета другого материала.** Светлый лепесток ошибочно
   сравнивался с более далёким бежевым материалом. Правильный локальный образец
   отвергался, а оставшийся усреднённый жёлтый цвет не проверялся. При удалении
   синего фона вычиталось слишком много синего: flower `(350,160)` превращался
   из RGB218/213/216 в218/212/127. Поздний `opaque_spill` мог повторно испортить
   уже исправленный цвет. Обе цепочки исправлены вv16;30постоянных тестов и
   full-source actual stages подтверждают ограниченный результат. Это не
   доказательство устранения всех остальных контуров.
2. **Ошибочное повышение непрозрачности и позднее перекрашивание.** У strings
   `(642,520)` восстановление текстуры поднимает alpha99 до255. Следующая
   цветовая коррекция отвергает восстановление alpha из-за выхода RGB за
   допустимые границы, но отдельно перекрашивает пиксель в92/85/70 приalpha255.
   Так появляется тёмная сплошная точка. Механизм прослежен; истинный foreground
   реальной точки неизвестен. Простое отключение восстановления портит
   контрольные сцены с настоящей краской, поэтому общего исправления пока нет.
3. **Повторное создание оттенка при нейросетевом увеличении.** После исправленного
   native flower NN-пиксель `(280,480)` получаетRGB239/195/185 приalpha159:
   интерполяция native без NN даёт примерно224/218/216. У duck `(121,168)`
   NN даёт123/94/102 против обычной интерполяции212/200/182 при одинаковойalpha172.
   Это подтверждает изменение на этапе NN, но не устанавливает истинный цвет
   каждой детали: NN также способен правильно восстановить настоящую тонкую линию.
4. **Слабые удалённые точки всё ещё влияют на NN.** Итоговая маска удаляет часть
   слабых точек, но рабочая маска сохраняет их для увеличения. RGB-only NN
   получает их цвет с полной контрастностью: например, flower workingRGBA0/0/0/2.
   Управляемый эксперимент, меняющий только RGB уже удалённых слабых точек,
   действительно меняет соседний видимый край при точном сохранении alpha.
   Однако на другом участке делает контур темнее. Вклад контекста подтверждён;
   универсальная безопасная коррекция не найдена.
5. **Ранняя оценка alpha в precise-ветке.** Новые частные known-truth сцены
   показывают ошибку покрытия ещё до восстановления текстуры: формула по
   разности ключевого и остальных каналов не учитывает цвет настоящего foreground.
   Локальная физическая оценка смеси улучшила контроль на3ключевых цветах до
   maxRGBAerror1. Это пока результат диагностики агента и частного прототипа;
   постоянная регрессионная защита и общая безопасная интеграция отсутствуют.
6. **Часть цветной линии уже нарисована в исходнике.** Например, strings
   `(657,540)` RGB188/118/132 проходит стадии неизменной. Нельзя приписывать всю
   розовую линию удалению фона или автоматически обесцвечивать настоящую краску.
   Дополнительно прежний divisor-floor на слабом покрытии давал математическое
   затемнение; его исправление и endpoint-защита сохранены вv16, это отдельная
   уже проверенная причина, а не объяснение всей нынешней каймы.

**Гипотезы и направления следующей проверки**

- Различать просвет с примесью фона и настоящую окрашенную линию по соседним
  исходным цветам, их изменению относительно ключевого цвета и независимым
  участкам подтверждённой краски. Пространственный кандидат улучшает darkpoint,
  но новый контроль с настоящим окрашенным участком выявил14повреждений:
  перед внедрением нужна защита подтверждённого пигмента.
- Проверить локальный физический fit до ошибочного восстановления opaque-alpha
  в precise-ветке. Не менять пороги выбора ветки ради прохождения одной сцены.
- Проверить более близкий сохранённый foreground вместо далёкого opaque-донора
  при обработке удалённого NN-контекста. Этот следующий вариант ещё не выполнен;
  предыдущий эксперимент дал смешанное визуальное качество.

**Отвергнутые сокращённые решения**

Полное отключение texture recovery, простая блокировка позднего перекрашивания,
общая десатурация и ограничение NN диапазоном соседних native RGB не приняты.
Блокировка заменяла тёмную точку синей, а ограничение NN портило известную
тёмную линиюRGB60/45/55 до195/191/194 при неизменнойalpha192. Равные исходные RGB
могут соответствовать разным foreground/alpha; одну интерпретацию нельзя
объявлять доказанной истиной только по совпадению с желаемым результатом.

**Локальные доказательства на VDS:** v16 и actual-проверки:
`../../artifacts/material-edge-fix-20261003/REPORT.ru.md`;
независимый разбор native/NN: `../../artifacts/remaining-edge-20261003/rim/REPORT.ru.md`;
управляемый NN-эксперимент: `../../artifacts/remaining-edge-20261003/nn-context/result.json`.
Далее нужны постоянные public RED/GREEN для нового дефекта, отрицательные
контроли настоящей краски/source alpha/legacy и одинаковые actual-сравнения
после всей цепочки. Прошедшие тесты и сохранение исходника не заменяют
визуальную приёмку всего края.


Владелец поручил продолжать после частичного materialv16 исправления. Frozen
v16 snapshot/SHA, branch/HEAD сохранены. Новые независимые факторы: spatial
source-colour evidence против false texture promotion и nearestopaque RGB
extension передNN. Не повторять rejected pairguard/blanketbypass/sum<=1.

CachedNN envelope factor:516duck/823flower strongsoft pixels ниже native
bilinear contributors более10RGB хотяalphaexact. Но blanketclamp knowntrue
darkstrokealpha192 превращает60/45/55→195/191/194; не внедрять. Это evidence
NN усиления, не доказанная foregroundcorrection. Product unchanged.


NN context private experiment меняет только RGB delivery0/working1..127,
working/delivery alpha и unselected preparedRGB exact. NewlocalNN2:
duck44.43с,flower41.46с. Flower239/195/185→226/223/221, ноduck265340
176/153/162→135/116/146 и контур местами темнее: universal adoption отвергнута.
Source/productsnapshotv16 exact; последующий localstrongdonor вариант ещё не
запускался из-за disk-full, успех не заявлять.

Spatial recovery candidate улучшает actualdarkpoint, но distinct-source
paintmarker negative выявил14новыхopaque повреждений; не внедрён.
Дополнительная cause: precise rawmatte ошибается до recovery на shadedgap;
private localphysicalfit даёт maxRGBAerror1 на3keys, однако общий кандидат
ещё не прошёл paintmarkernegative. PermanentRED/productionfix пока нет.

Среда была193ГБ/100%, ordinarysandbox не запускался. Удалены только
регенерируемые privateNN inputs и временные фикстуры завершённых нашихpytest
564/565/566; JUnit/source/model/evidence сохранены. Agentreadonly escalation
не состоялась из-за timeout automaticapprovalreview; после routinecleanup
readonlytrace выполненаобычнымsandbox. Каталог /tmp/vibix-size-audit/extracted
без ответа владельца не удалялся. Сейчасdisk89ГБfree, блокер снят внешним
изменением среды; root не объявляет это собственной очисткой1.5ГБ.

## material-edge-fix-20261003

Владелец разрешил реализацию после диагностики edge-root-cause-audit-20261003,
сначала tests и затем исправление. Verifiedv15 snapshot/SHA/ветка сохранены в
`../artifacts/material-edge-fix-20261003/baseline-v15/`. Новые corrections
только после permanent public RED; sourcealpha/legacy/genuinepaint/additive/
широкие contaminated rims остаются обязательными negatives. Groundtruth
AA/opaque twins с одним wholeRGB требуют явной согласованной policy, не
невозможного двойногоPASS. Исходная causal история сохранена ниже. Реализация
и проверка нового правила в работе, успешный visual результат ещё не заявлен.

Permanent public RED до новых source правок: tests/test_chroma_material_causality.py,
6FAIL/18PASS, отдельно old localmaterial57PASS. Фикстура и expectations после
RED не менялись. Доказательства ../artifacts/material-edge-fix-20261003/tests/.

Гипотеза restrict scale+b<=1 → private prototype → true key-contaminated
highlight F1.1*core,a.8 меняется198/176/110/204→162/150/136/255: отвергнута.
Гипотеза restrict scale<=1 → gamma1.25,a.95 имеет scale1.1875: отвергнута.
Это диагностические prototypes, не две production правки одного дефекта.

Новый fallbackvalidation → прежний deeper fit сам по себе не оправдывает
retained Gaussian/reference другого материала. Local candidate отвергается,
только если retainedfallback проходит те же residual/gamut mixture checks.
Late opaque_spill получает source-local prior через ту же проверку. Оба правила
только opaque_clipart+whole sourceA255; legacy/suppliedalpha old route exact.
Product chroma_rim.py/main.py unchanged verifiedv15; внутренний профильv16,
API1/schema/appversions unchanged. Candidate source chroma_key SHA d904c4803cbd08ac48469582887f6b29dba265571c0f4ce5af4e4eb5efb14fc8.

Root fullnative3 + real host/finalwriter → sourceSHA unchanged, deepcoreRGBA
unchanged, components unchanged, trimpositive loss0, actual PNG/DPI/receipt
pass. Flower4 problematic samples теперь exactsource through all late stages,
actual yellow patch визуально уменьшен. Это не universal foreground truth.
Strings697708 ранее58/48/176/255, теперь late repair126/102/86/118 → прежний
cleanup alpha0. Ещё2weak samples становятся255. Новый material prior косвенно
меняет later supports; strongpaint invariance не доказана. Private trace и
knowntruth boundary probes в работе, никаких blind texture bypass изменений.

Разделённые проверки: chroma626tests+40subtests PASS (106.16с), benchmark19tests+6subtests PASS, component/host/editor/
validation129tests+10subtests PASS,1skip WindowsNN (папка отсутствует),1Pillow
DeprecationWarning. Inherited UI padding1PASS. JUnit отчёты в private artifact.
Первый combined broad run завершилсяexit143 после17dots безsummary, причина
сигнала пока неизвестна; не засчитанPASS. Повторные группы выбраны из-за
незавершённого прогона, successful subsets безновыхправок не повторяются.

Root первый broadpytest invocation выбрал неверный node без класса: collection
exit4/no tests. Исправлено, rerun в работе; inherited UI padding node cклассом
V3ClipartFlowTests отдельно1PASS. Agent premature broadrun остановлен exit130,
не считаетсяPASS. Network sockets failfast, сборок/скачиваний нет.

Root actual localNN2 execution на новом working input, существующие executable/model,
без скачиваний: duck46.83с/flower47.04с, output768²; deliveryalpha exact,
sourceSHA unchanged, profilev16/finalPNG receipt PASS. Fullsource native solve
перед crop доказан отдельно; chroma solve на маленьком crop не подменяет его.
Actual NN boards визуально показывают уход yellowpatch, thin pink/gray outline
остаётся. Это cropNN, не новый полноразмерныйNN или installedWindows test.

Независимое review обнаружило недостаток новых регрессий: targeted latepolicy
ablation preserve_local_material=False оставляет все18shapedfixtures byteexact,
lateopaque_spill там меняет0пикселей. Старые additiveedge тесты также не
упражняют новуюlate ветку, benchmark opaque-spill использует defaultlegacy.
Это P2 missingacceptance, неPASS всей late policy. Новая publicknowntruth
late fixture + activelate negative в работе у testowner; старые24 expectations
не менять. Evidence ../artifacts/material-edge-fix-20261003/review/late-policy-ablation.json.

Late coverage закрывается новыми6public regressions, старые24byteprefixexact:
positive3earlystagedtruth→late/finaltruth, negative3uniform252/246/210 opaque
surface+.14K reflection217/212/216 staged→late252/246/210255. Root6PASS,
agent targetedoldlate3FAIL/3PASS, whollydisabledlate3negativeFAIL. Тесты не
зависят от privateartifacts; доказательства RED есть отдельно.

Privatetexture36 independentopaque key-hued stroke probes (3core×4gaps×3lengths)
→ v15FAIL/v16FAIL whole targetexact; новыйknowntruthregression не обнаружен,
но исходное genuinepaint требование для этих сцен не выполняется.3keys
identical-source AA153/opaque255 twins: output выбирает opaqueinterpretation;
нельзя одновременно объявить обе recovered. Pairguard rejected:43oldrimtests
PASS, ноactual4RGB changes dark→blue, alphaexact,642520blue229 вместоdark70,
697708 по-прежнемуalpha0. Это не matte fix, product не менялся.

Завершённые root группы:626chroma+19benchmark+129components+32transportAPI+
1inheritedUI+6late=813distincttests PASS,77subtests PASS;1WindowsNNskip/
1PillowDeprecationWarning.30newtests внутри этого числа, повторные agentruns
не добавляются.36diagnostictruthFAIL не включены и не скрываются behindPASS.
AST parse/diff-check PASS; main.py/chroma_rim.py exactv15 baseline.
Исходникиactual3 SHA неизменны; новые actualNN2 executed, не cached replay.
No newnetwork/paid/download/build/deps/commit/push. Actualwholevisualquality
остаётся частичной: yellowpatch fixed, strings darkpoint/thin colouredrim и
1previousstrong alpha loss требуют нового доказанного решения.

Независимый finalreview addendum: currentlate6PASS; oldlatepositive3FAIL/
negative3PASS; fullydisabledlatepositive3PASS/negative3FAIL. CoverageP2 закрыт.
Negative target глубже3pxlocalreplacement и защищает activeinterior despill,
не все contourmixture interpretations. Strings strong-support loss и вся
остаточнаякайма остаются открытыми, generalvisualapproval не объявлена.

## edge-root-cause-audit-20261003

Владелец просит сначала установить причины остаточного плохого края и способы
решения, затем приступать к новой правке. Применён systematic-debugging, два
независимых gpt-6-astra/xhigh и отдельный challenge прежнего gpt-6-astra/high.
Product/tests заморожены на прежнем v15, рабочая ветка/HEAD сохранены. Причины
прежних numeric/admission/NN-working-input исправлений не обнулять. Новый итог:
`../artifacts/edge-root-cause-audit-20261003/REPORT.ru.md`.

Гипотеза foreign-material prior → full-source flower internal trace → actual
350160 source218/213/216 становится218/212/127/255 до первого observer.
Local352158=245/240/225 отвергнут одним wider-depth12 sample370164=227/217/197:
b.03927,residual2.996<=10.914. Остаётся Gaussian229/198/126; early_rim demotes
core и первый unmix вычитает B. Поздний key_edge сохраняет раннее решение.
Target-only runtime замена firstprior на actuallocal → firststaged sourceRGB;
но следующий opaque_spill повторно меняет350160 в252/246/210/255. Следовательно
firstprior fix сам по себе недостаточен. Native mechanism.json и
actual-interventions.json; source actualFG не объявлять известной истиной.

Независимая petal truth → public automatic control с истинным opaque218/213/216
и дальним бежевым painted sample → staged226/221/160/241, final233/227/213/239.
Подмена только первой localreference либо изменение только дальнего sample
восстанавливает exact truth; blue/green/red подтверждены, root независимо
повторил blue. Это ошибка выбора материала, не oldfloor/endpoint. Отрицательная
граница: те же entireRGB допускают genuine additive F218/212.4/140.1+.3K;
blanket preserve-local проигрывает эту интерпретацию. Новое правило не внедрено.

Гипотеза false opaque promotion → full-source strings642520 trace →
C92/70/229 → firstunmix238/178/191/a99 → recovery92/70/229/a255 →
repair92/85/70/a255. _recover_opaque_texture_matte bridged=True, depth10.19,
nearestcore227/176/129 residual23.56>5; это провоцирует matte=1. _extend_runs
здесь не меняет mask. Repair отклоняет coverage recovery из-за recoveredR263.51,
но сохраняет отдельный colour_repair. Запрет только promotion в target →
final238/220/182/95; истинный actualFG остаётся неизвестным.

Strong shaded-gap truth → K0/2/253, opaque берега240/210/160, shaded F120/105/80,
truealpha153, C72/64/149 → baseline72/64/149/255; bypass только recovery даёт
120/105/80/151, RGB exact,alphaerror2. Подтверждены3 key permutations и root
независимый repeat. Новый результат не получается за счёт weak cutoff: alpha151
сильная. Однако whole sourceRGB точно совпадает с возможной настоящей opaque
painted line72/64/149/255. Blanket bypass её разрушает. Ранее пробованный более
яркий .6 control не сдвигался bypass из-за earlier promoted; оставлен как
неуспешная абляция, не засчитан в proof. Native texture-strong-control.json,
truth-negatives.json, root/repeat-verification.json.

Reference сравнение → flower350159/350160 core, firstunmix bypass → меньший
yellow дефект, но adjacent377155235/227/217→238/230/148 иззаdeep material mix.
Fixed v15alpha +referenceRGB уменьшает метку, но желтит соседний лепесток.
Strong shade/pink/greenAA153/191 controls ломаются в обоих алгоритмах после
classifier. Finish не исправляетRGB, islandcleanup может удалятьalpha255
соседнего большого объекта.31 diagnosticassertions PASS, actual3 reference
byteexact прошлым outputs. Это не доказательство правильного unknownFG и не
основание копировать reference strategy. AGPL runtime/source не переносились.

Cached actual NN vssamealpha interpolation → duckcropNN265340 RGB161/135/149,
a155 противbilinear192/165/178 иpremult194/167/179 → NN усиливает darkcontrast,
но source hue остаётся и в обычном resize. Это прежний NN вклад, а не заново
внесённое v15 workingmask затемнение. Новый NN не выполнялся. Реальный Qt100%
vsPIL наknowncolour/actualNNwhiteblack → max0/1RGB, ниоднойdiff>1;
constantcolour/bilinearalpha RGBexact/rings0. Doublepremultiply/viewer причина
наtestedpath не подтверждена. Часть pinkline source есть уже до всехstages:
strings657540188/118/132 иduck841495235/199/188 остаютсяopaque exact.

Следующая обоснованная область: выбор/отклонение материала до firstunmix И
повторная проверка material evidence вopaque_spill. Отдельно после неё matte
promotion/lateRGBalpha согласованность, затем NN. Широкую обрезку/глобальное
перекрашивание/безусловный bypass не внедрять. Нужны новые public knowntruth,
existing13–14px contamination negatives, genuineopaque/additive/keypaint,
shade/colourAA/gaps/sourcealpha/legacy и actualwholeimage checks. Challenge
подтвердил причинность и отсутствие ещё доказанного универсального правила.
Универсальная visual quality остаётся открытой; code/tests/SHA исходников
не изменены, docsSTATE/TASKS обновлены. Новыхnetwork/paid/download/install/
dependencies/build/NN/commit/push/merge нет.

## strict-opaque-edge-20261003

Владелец явно ответил «Да» на предложение допустить потерю самых слабых штрихов
ради более чистого automatic края. Это изменение требований, а не разрешение
выдать старую потерю истинного AA за точное восстановление. Предыдущие причинные
данные: #automatic-core-reference-cause-20261003 и historical/reference reports.

Новая проверяемая гипотеза: source hard-background boundary, уже admitted в
старом classifier, можно отсечь после последнего colour refinement, сохранив
RGBA всех survivors. Early rollback перестраивает references и меняет surviving
RGB. Независимый prototype fullpartial final cull убирает4397/8720/8905 pixels,
но среди них естьalpha133/208/240 и внутренние partial pixels; весь этот объём
нельзя назвать «самыми слабыми». До production задаём предел finalalpha1..127
(background majority), source1px boundary, whole sourcealpha bypass и legacy
exclusion. Оpaque/core и более сильная coverage не должны меняться. Отдельно
проверяем обе public branches и later/NN stages, так как inputRGB под новойalpha0
перестраивается `_prepare_upscale_rgb`. История/доказательства этой итерации:
`../artifacts/strict-opaque-edge-20261003/`, baselinev14 сохранён отдельно.

Первая production итерация → native3/source/allRGB/alpha>=128 exact и removal
4396/8683/8876 → четыре настоящих cached NN192→768 before/after → native слабая
бахрома уменьшается, но NN усиливает новую тёмную линию. Подтверждённое сравнение:
duckNN(276,381), alpha221 одинаковая, RGB234/209/183→162/115/104; все четыре
native contributors818..819,434..435 не менялись и имеют alpha159..255.
Контроль cachedv14 NN RGB + v15 deliveryalpha уменьшает новую линию при той же
mask. Причина: новое alpha0 меняет `_prepare_upscale_rgb` и вход/context NN,
а не неверный новый RGB самого chroma. Расширение cutoff на весьalpha1..127
не убирает плотную линию и теряет дополнительно552 true linepixels; отвергнуто.
Доказательства: review/RESIDUAL-NN-REVIEW.ru.md, delivery-verification.json,
duck/flower-nn-before-after.png. Старый renderer/input protection не ослаблять.

Следующая обоснованная правка: в памяти вернуть вместе с v15 result исходную
L-alpha до cleanup. Только host local upscale_after реконструирует отдельный
working RGBA с прежней alpha, применяет существующие prepare/NN и тот же working
pretrim к deliveryalpha. Новую deliveryalpha восстанавливать после NN, до edge
cleanup/finaltrim. Pixel API1 и старые компоненты без hint остаются прежними;
hint не сериализовать в PNG/project/receipt и не переносить между заданиями.
Проверка: fake NN утверждает exact v14 подготовленныйRGB и crop; actual cached NN
при том же input/model должен вернуть прежнийRGB при новой deliveryalpha. Это
исправление найденного нового P2, не заявление об устранении остаточной native
каймы. До этой проверки кандидат не готов для принятия.

Новый транспортный test harness сначала не выставил `upscale=False`. Default
Worker запустил KIE pre-upscale/upload path; девять tests FAIL на DNS failure,
задача KIE не была создана. Это ошибка стенда и попытка network, не корректный
RED программного дефекта и не полностью offline run. Настройки исправлены;
в стенде все provider/upload/download entry points заменены fail-fast guards.
Отдельный `red-nn-transport-safe.log` является безопасной исходной регрессией.
Первый лог сохраняется для аудита; не считать его доказательством offline PASS.

Transport реализован → безопасная исходная регрессия дала5FAIL/4PASS → после
исправления и дополнительных bounds/reuse проверок19 transport tests PASS.
Optional hint извлекается до PNG save; отдельная workingalpha передаётся только
local post-cutout NN. Crop обеих масок использует один bbox. После NN существующий
resampler ставит deliveryalpha до дальнейшей обработки/trim. API1/prepare/NN/
alpha-restore/trim helpers не изменены. Legacy/sourcealpha/no-hint не требуют
нового протокола. Уже сохранённый cleaned PNG не содержит прежнюю workingalpha.

Независимый transport review нашёл2P2 → проверка type/L/size, delivery<=working,
каждого изменения толькоworking1..127→delivery0 и непустой delivery до NN;
дополнительная проверка конечной alpha после restore → те же3 failure probes
теперь ValueError до NN;27 focused transport/provenance tests PASS. До этой
правки malformed hint мог обрезать сильный opaque остров, а allzero delivery
могла пройти по непустой workingmask. Новых P1/P2 reviewer не нашёл. Последняя
root группа51 mask+transport PASS. Подробности review/TRANSPORT-REVIEW.ru.md.

Corrected host →2 НОВЫХ настоящих offline crop NN192→768 на уже проверенных
full-source native crops → preparedRGB и actual NN RGB побайтно совпали с прежним
v14; новая deliveryalpha, PNG300DPI и hash-bound receiptv15 PASS.45,52/47,13с,
fixed-crop-nn/verification.json. Root и независимый reviewer просмотрели оба
финальных before/after: усилившаяся новая тёмная линия исчезла, слабой бахромы
меньше. Это не повтор chroma на неполном source-frame. Thin pink/gray/cyan line
местами остаётся, пушок/кончики теряются, некоторые границы жёстче/ступенчатее.

Новый полный actual NN run → workingRGBA/preparedRGB577×1181 exact старому
проверенному входу → timeout600с, нового full NN output нет. После этого current
pipeline выполнен с ранее проверенным реальным cached full NN payload, при том
же входе. Full cached replay → NN RGB и deliveryalpha exact; final2402×4816,
padding48px со всех сторон,300DPI, sourceSHA/receipt/interior PASS, trim loss0.
full-pipeline/verification.json подтверждает только вход; полный transport/writer
подтверждён full-cached-replay/verification.json. Не выдавать replay за новый
полный NN execution. Installed Windows/remote providers не проверены.

Final native3 → removal4396/8683/8876, allRGB/alpha>=128 exact;135 public legacy/
suppliedalpha comparisons exact. В8 independent GT scenes удаляются только
truealpha<128, strong/opaque loss0; потеря настоящих слабых AA намеренная.
Source1px boundary не равна final silhouette1px: components1→2/4→40/1→8,
removed olddepth>3:168/835/897. Существующий crop flower final trim дополнительно
обрезает6 veryweak samples; не обещать lossless geometry. Profilev15, receipts
v1–v14/component/API1/UI padding contract PASS. Aggregate782 distinct tests
+51 subtests PASS,1 Windows NN skip,1 старое Pillow warning; это scoped groups,
не full-project suite. Syntax/sensitive/diff-check PASS. Финальная независимая
оценка: review/FINAL-VISUAL-REVIEW.ru.md; root итог: REVIEW.ru.md в тех же private
artifacts. Вся остаточная visual quality задача открыта; сборка, установка,
downloads/dependencies/commit/push/merge не выполнялись.

## automatic-core-reference-cause-20261003

Владелец повторно попросил causal automatic fix по скачанному образцу и сильных
агентов. Продолжаем с уже доказанной historical admission причиной и негативами,
не объявляя ручной retouch или precision fix устранением globalrim. Прежние
доказательства: `../artifacts/historical-edge-causal-20261003/REPORT.ru.md`,
`../artifacts/edge-precision-20261003/REVIEW.ru.md` и
`../artifacts/reference-edge-causal-20261003/`. Blanket classifier rollback,
residual admission guard и недостоверный affine background prior не внедрять
по прежним опровергнутым предпосылкам. Новый branch/requirements вSTATE.md.
Два независимых gpt-6-astra/xhigh завершили исследование. Новые доказательства:
`../artifacts/reference-core-cause-20261003/reference/REPORT.ru.md`,
`../artifacts/reference-core-cause-20261003/vibix/REPORT.ru.md` и root/REVIEW.ru.md.
Reference read-only AGPL research, без переноса source/runtime в закрытый продукт.

Причина чистого края reference → точечная проверка → результат:
classify.ts:28/31 помечает named pixels фоном до solve → force admission только
duck821,435/837,470 после classify, referenceF не меняется → reference возвращает
зелёные222/230/179/45 и203/248/184/53. Из текущего native support classifier
удаляет4397/8722/8910 pixels до finish; pocket0. На ground truth он удаляет
7 genuine AA rows и960/8004 visible outline/line pixels; suppliedalpha128→255.
Copy/rollback classifier не удовлетворяет требованиям краски/coverage.

Новая независимая числовая причина → минимальная правка → проверка → результат:
strict0..255 позднего explained guard отвергает float32 overshoot valid endpoints
→ finite и bounded4eps*255/max(a,.025) tolerance<0,005 RGB, только originalalpha255,
с прежним source reconstruction≤2 → baseline57 exact cases30FAIL/27PASS,
candidate57PASS; knownF200/200/0 вместо212/212/0 и publicalpha26/51 вместо25/49.
Root включил отдельно проверенную weak/v13 precision поправку в combinedv14;
исходный worktreev13 оставлен неизменным. Weak solved→weak→valid indices и mixed
tile512 cases проверены. Legacy/sourcealpha/out-of-gamut/additive/noise guards
сохранены.658 tests+51 subtests PASS,135 root exact negative comparisons PASS,
old receiptsv1–v13/components/API1/UI padding contract PASS. Release versions
не менялись, commit/push/merge/build/network/paid/download/install не выполнялись.

Combined actual3 production v14: все1254² RGBA byteexact v12, core>3/support
components1/4/1/sourceSHA exact. Это доказывает отсутствие визуального улучшения
всей полоски. Root просмотрел dark/white reference абляции и known-shade before/
after. Настоящий final writer3 trim+1%padding+300DPI/hash-boundv14 receipt PASS
внутри существующей trim области. Первая проверка writer предполагала bboxalpha>0
и FAIL толькоstrings; причина установлена: старый _detect_alpha_trim_bbox использует
alpha>12. В strings обрезается1 pixel(1010,280)alpha3, width657→656 доpadding.
Проверка скорректирована к задокументированной policy с явным счётчиком потерь;
не утверждать lossless final support. Native equality не закрывает geometry всей
pipeline. Нового NN/installed Windows/end-to-end customer acceptance нет.

Открытые подтверждённые P2, повторены root наv14:
1. hiddenRGB alpha0 влияет на прямой automatic API: одинаковые видимые source
pixels дают pixel(48,20)alpha0 либо64 в зависимости от невидимого hole RGB.
Classify/reference игнорируют original alpha при выборе subject. Default main
usable-alpha bypass ограничивает воздействие; actual3 originalalpha255 не связаны
с этим defect. Простая заливка hiddenRGB key теряет genuine AA и не является fix.
2. White-AA F255/255/255,a.25,K0/0/255,C64/64/255 рядом с warm core240/210/130
даёт226/226/130/72. mixture_coverage трактует impossible borrowed-prior fit как
additive, но невозможность prior не доказывает additive. Identical source также
имеет genuine additive truth F240/240/130,a64/240,extra key≈.13072: blanket
ordinary/saturation preference ломает отрицательный случай.
3. Контроль mild local background drift B255→245 при frameK255, truthF200/150/80,
a.2 возвращает173/130/69,a59 вместоF200/150/80,a51. Reference raw-alpha при
forced admission спасает12 drift controls, но genuine shadeF100/75/40,a.4
ошибочно превращает вF200/150/80,a.2. Общая модель C=αγFref+(1−α)βK определяет
s=αγ,b=(1−α)β, но не α/γ/β отдельно. У actualduck837,470 даже convex combination
локальных hard-background RGB не объясняет warm paint: sourceG−R11 противmax4.
Alpha-only correction не восстанавливает этот hue; foreground unknown.

Отвергнутые private попытки этого исследования: nonkey hue-sign projection
сохраняет alpha, но genuine green82/160 становится121/121 и pink254/112 становится
183/183; длинная actual полоска сохраняется. Physical saturation/b clamp спасает
часть white truth, но запускает strict-float guard/late override и конфликтует с
identical additive negative. Пороговый sweep/production adoption этих policy
гипотез не выполнялся. Следующее исправление всей каймы должно иметь новые
независимые данные о material/background; не повторять эти опровергнутые priors.
После конкретного сравнения historical duck-admission-comparison владельцу задан
вопрос о продуктовой допустимости потери слабых штрихов. До явного ответа это
не разрешение на удаление known true AA или изменение согласованных проверок.


## low-coverage-colour-20261003

Новые данные после ранее отвергнутых B-field/тоновых/neighbor-fill вариантов:
в первом staged solve есть floor denominator 0,05. Для известного F=(200,150,80),
coverage=0,04, key=(0,0,255), exact composite C=(8,6,248), код возвращает
RGB=(160,120,64). Позднее coverage восстанавливается, но тёмный RGB сохраняется.
Это самостоятельная числовая ошибка, а не доказательство unknown paint на всей
реальной полосе. Три key permutation воспроизведены главным агентом в baseline:
15/18 новых known-truth tests FAIL, 3 PASS.

Причина → минимальное изменение → проверка → результат: denominator floor
для positive weak coverage → деление на actual coverage только opaque_subject,
0,025<a<0,05, ordinary a+b≈1, original alpha255, signal/a внутри0..255 →
255 связанных тестов PASS. Floor сохраняется для невалидного/out-of-gamut,
additive, supplied alpha, discarded noise и legacy. Alpha здесь не меняется.
Private baseline code/script сохранены в low-coverage-colour-20261003.

Actual native уточка/цветок/ниточки:408/579/594 изменённых пикселя; исходный SHA
не меняется, inner RGBA глубже3px exact, visible→zero0, число connected visible
components совпадает. Два настоящих cached Clipart NN192→768 на Linux software
Vulkan15,73/16,24с; final trim+1%padding+300DPI PNG interior RGBA roundtrip PASS.
Просмотр dark/white показывает: длинная полоска остаётся, не заявлять полный fix.

Отдельный новый эксперимент: original RGB crop → cached Clipart NN4 → chroma
(32px measured global key frame после NN только для border estimator) против
production cutout → NN. Край резче, но появляются насыщенные magenta/green полосы,
black gaps/отделённые кончики, на цветке yellow/green leaf rim и pink tips.
Root и независимый агент просмотрели dark/white boards: отвергнуто, не production.
Настоящий foreground без исходной прозрачной ground truth нельзя установить
из одних generated composite RGB; lowering dominance/early_rim guards может
перекрасить настоящий контур, поэтому threshold changes не внедрялись.

Доказательства вне Git: ../artifacts/edge-order-20261003/ и
../artifacts/low-coverage-colour-20261003/. Независимое ревью P1/P2нет;180 квантованных cases +180 legacy exact,30 sourcealpha,
18 additive,9 dark-outline equivalence PASS; root повторил полный audit PASS.
Algorithm identity обновлён доv12, API1/старые receipts совместимы, versions
программы/модулей не менялись. Отдельные49 tests PASS:30 новых positive/negative,
8 provenance,10 selected component compatibility,1 internal padding UI contract.

Первый общийsafe run2590PASS/1FAIL: UI field coverage test устарел после31da612
(internaltrim_padding_percent требовалwidget вопреки одобренному fixed/noUI).
Причина → актуализирован список internal exclusions и добавленыassertNotIn
widget/default0 ordinary → failingtest+related49 PASS. Ни одна пользовательская
настройка не исключена, прежнее exact field equality сохранено.
Повторныйfull safe run2591 tests +284 subtests PASS,57skip/21networkpaid deselect,
1 прежнееPillow warning,385,22с. 12 guards appended послеcollection полного run;
отдельный49-targeted включает все30 lowcoverage cases.

Полныйsource1254² actual WorkerThread pipeline: localchroma → pretrim577×1181 →
realcached Clipart NN4 → final2308×4724 +48eachside →2404×4820,300DPI.357,72с.
Inner cropped RGBA/sourceSHA unchanged,zero padding alpha,profilev12/hash-bound
receipt,manual_transparency_requiredFalse PASS. Root просмотрел edge-dark-white:
длинная линия остаётся. Evidence ../artifacts/low-coverage-full-pipeline-20261003/.
Это Linux local source-to-PNG проверка, не installed Windows/customer licensing.
Staged sensitive scan иdiff-check PASS.
Сборка, сервер, лицензии, releases, downloads, paid calls не запускались.

## final-trim-padding-20261002

Владелец уточнил: речь о transparent canvas padding после trim, а не мягкости
alpha края. Проверены official Photoshop Trim/Canvas Size, ImageMagick border,
Adobe Stock PNG best practices: обязательной нормы1–2% не найдено; standard
trim обрезает до видимой области, padding задаётся отдельно. Владелец одобрил
нашу policy1% длинной стороны trimmed object на каждой стороне. Источники:
https://helpx.adobe.com/ca/photoshop/using/adjusting-crop-rotation-canvas.html
https://usage.imagemagick.org/crop/#border
https://helpx.adobe.com/in/stock/contributor/submit-your-content/submit-pngs/png-best-practices.html

Реализация: внутренний persisted trim_padding_percent0default/1automatic;
правило включается до restore/retry, default0 не добавляется в worker plan,
чтобы не менять старые non-automatic request fingerprints. Padding выполняется
после final trim на unpublished staging PNG; pattern/manual transparency/
trim-disabled исключены тем же trim gate. ceil(longside/100),minimum1px,
Image.newRGBA и paste без mask сохраняют RGBAexact; source закрыт до записи.
Metadata через общий PNG writer,300DPI verify и atomic publication после padding.
Pre-upscale crop не содержит padding. Старые completedoutputs не переписываются.

Focused8 checks PASS: large/portrait/fractional/small dimensions, partialalpha,
repeat no accumulation, pattern/manual/disabled trim, state roundtrip. Actual
supplied5016²: trimmed2308×4722, padding48eachside, output2404×4818,DPI299.9994,
inner croppedRGBA exact/sourceSHA unchanged. Private verification:
../artifacts/final-trim-padding-20261002/verification.json. State/queue/export/
metadata suite:110 tests +43 subtests и125 tests +40 subtests PASS.
Добавлены regression cancel/write failure с сохранением предыдущего output
и source; финальные30 tests +21 subtests PASS. Независимое ревью новых P1/P2
не нашло. Главный агент прочитал diff и повторил7 независимых QA-сценариев
из `/tmp/audit_final_padding.py`: default request compatibility, upscale order,
metadata/ICC/XMP cleanup+receipt final digest, blank alpha, atomic cancel/write
failure, actual Qt old restore/saved-source retry PASS. Staged sensitive scan
и diff-check PASS. Windows/настоящий новый neural upscale не проверялись.
Кайма/сборка не затрагиваются.


## late-boundary-colour-20261002

Новая диагностика после repeated-despill guard: `_refine_opaque_boundary`
повторно проецирует источник на более яркую соседнюю краску без brightness.
Точный контроль K=(0,0,255),core=(220,220,220),F=(210,210,210),a=.2,
source=(42,42,246): staged=(210,210,210,46),late=(219,219,208,49),final
тот же. Прямой exact provisional=(210,210,210,51) тоже портится; причина
не зависит от первого матта или неизвестного фона. Golden контроль
F190/171/95,a=.2 →196/176/90; смена key-канала воспроизводит ошибку.

Гипотеза → существующий RGB уже объясняет source с другим покрытием после
alpha remap → scratch guard free coverage/source-residual≤2 и близкий fit.
Первый вариант сохранял RGBA целиком:48 exact controls/48 legacy controls
PASS, но187/190 scoped checks PASS,3 FAIL (red/green AA98 вместо102±2,
golden opening mean14.2985 вместо<12). Не внедрён: freezing alpha блокирует
полезное уточнение покрытия. Новые данные обосновывают раздельную проверку
RGB и покрытия, не ослабление прежних тестов. Production пока не изменён.

Второй scratch: сохранить RGB и refit alpha →98/99 PASS, openings всё ещё
FAIL14.2985. Новая трасса openings:805/805 partial provisional RGB самосогласованы,
но ошибочного оттенка, например F146/100/146 при reference239/158/72.
Отклонение от scalar reference48–96 уровней. Source consistency сама по себе
не доказывает правильный foreground. Следующее изменение обосновано этими
данными: guard только для RGB, отличающегося от reference scalar яркостью
(max residual≤2), source residual≤2 и fitted coverage в пределах.03 от prior.
Это сохраняет уже найденное затенение, одновременно refit alpha; прежняя
reliable/component/distance/sourcealpha защита остаётся, остальные пиксели
проходят исходную correction. Нет нового цвета из соседнего материала.

Production guard:39 новых direct/public/negative regressions; baseline18 FAIL,
21 PASS. После правки229 связанных tests PASS20.38с. Independent96 exact
palette +96 sourcealpha controls PASS; 3negative controls остаются исправляемыми.
Фактический diff-review: P1/P2 нет;3 greenleaf controls byte exact,3 shadedcusp
база портит11 pixels, production сохраняет; endpoint alpha безопасны. Root
повторил proof script. Обычный Python без cv2 не импортировал модуль при
переносе prototype; файловая правка тогда не выполнялась. Перенос выполнен
проектным venv, фактическая production regression GREEN подтверждена.

Actual production neural проверен отдельно: full native output совпал с
прошедшим prototype; final изменения duck20/flower34pixels. Ни одного
visible→zero; RGBA opaque body глубже3px exact. Настоящие existing cached
Clipart NN192→768 на двух фрагментах:24.24с/29.53с, alpha сохраняется backend,
реальный final writer trim+300DPI и PNG crop-RGBA roundtrip PASS, sourceSHA
unchanged. Root просмотрел dark/white: затенённая краска защищена, но общего
исчезновения длинных dark/colour lines не видно. Не считать20/34 изменений
доказательством идеального foreground или исправления всей каймы. Это
доказанный малый late-stage bugfix; неизвестный первый matte/внешняя source
обводка остаются нерешёнными. Full5016 NN/native Windows не проверены.
Данные ../artifacts/late-shade-neural-20261002/verification.json/boards.

Финальный общий safe suite на actual production source:2563 tests +284
subtests PASS за374.75с;57 skipped,21 network/paid deselected,1 прежнее Pillow
warning. Ничего не устанавливалось, модель не скачивалась. Проектные версии,
production/server/licenses и опубликованные пакеты не менялись.

Root native scratch whole-RGBA guard: duck376/flower399 blocked late edits,
373/396 final pixels changed; sourceSHA unchanged. Это числовая диагностика,
не доказательство качества каждого изменения. Private evidence:
../artifacts/late-boundary-colour-20261002/; /tmp/audit_remaining_matte.py/json.


## auto-clipart-trim-dpi-20261002

Подтверждение: supplied utochka_v_prazdnichnom_01_ready.png5016² не содержит
DPI, alpha bbox(1387,88,3713,4829). Automatic controller принудительно включал
remove/upscale, но оставлял trim/export_300_dpi=False из default/state. Общий
worker обрезал только после upscale. Исправление: automatic delivery flags при
install/navigate/start/restore, crop nonzero-alpha bbox до upscale_after,
сброс старого remote URL после crop, final trim остаётся.

Проверка выявила связанный дефект: плотный RGBA crop с белой краской стал
fully opaque; alpha final trim включал почти-white fallback и срезал краску.
Fallback теперь только для исходного формата без explicit A; explicit white
trim остаётся доступен. Регрессия включает белую краску, новые transparent
поля после upscale,300DPI/source unchanged, alpha1 и pattern canvas.
Независимое ревью выявило старый restore/retry flags bypass; нормализация
restore закрыла его, реальный reopen+preview_retry independent PASS.
Первый прогон:62 tests PASS,3 FAIL (2 новые неверные fixture assertions и
существующий settings-change test менял теперь обязательный trim). Исправлены
проверки: white defect устранён в production; shell через actual view; settings
provenance проверяется по свободному unsharp, не по обязательному trim.

Actual final writer suppliedPNG:2308×4722, DPI299.9994, cropped RGBA exact,
sourceSHA unchanged. Отличие bbox от alpha.getbbox связано с существующим
final threshold12; перед upscale используется любой nonzero alpha.
Независимое повторное ревью:7 safe scratch PASS, новых P1/P2 нет.
Private evidence: ../artifacts/auto-clipart-trim-dpi-20261002/.
Остаточная RGB кайма не исправлена этой задачей. Старые готовые файлы не
перезаписываются при reopen. Платные/model-download/Windows/build проверки
не выполнялись. Релевантный safe suite:203 tests +63 subtests PASS за137с;
1 skip Windows binary,1 прежнее Pillow warning. Дополнительный финальный
run11 tests +21 subtests PASS за3,85с.


## parallel-capacity-timing-20261002

Общий safe suite после RGB-защиты: 2520 tests PASS, 280 subtests PASS,
1 subtest FAIL (maximum KIE2 вместо3), 57 skipped/21 deselected, 426,29с.
Production генератор не менялся. Тест считал, что mock recordInfo задержки
40мс гарантируют overlap всех трёх потоков, что неверно при медленном startup.
Тот же FAIL воспроизведён без нейросети: delay .2с в ProviderActivity.start
для каждого третьего item; один test FAIL за1,642с.

Попытка1: удержать fake запросы release-событием до started_target=limit,
запустить worker в executor и release в finally с future.result для ошибок →
обычный модуль31 tests + 7 subtests PASS за7,91с, но тот же skew FAIL за1,331с.
Новые данные: task_count резервируется до activity.start; третий созданный
запрос может задержаться, а другой с task_count≥3 сигналит started при
только двух реальных операциях. При прежнем коротком mock это скрыто.

Попытка2: отдельный started_count после завершения activity.start под
существующим tasks_lock; task_count сохранён для task IDs/waves. Доказательство
того же skew: PASS за1,948с. Peak equality maximum==limit не ослаблялась,
генератор/реальный сетевой код не менялись. При недостижении мощности release
в finally освобождает fake tasks, исключения worker передаются через future.
Полный модуль после final helper correction: 31 tests + 7 subtests PASS
за8,12с. Независимый event-gated контроль подтвердил actual2→startedFalse,
actual3→startedTrue; подмена capacity2 при настройке3 всё ещё обнаруживается,
внешний RuntimeError передаётся в тест, release установлен и active0 после
обоих negative controls, real opener не вызывался. P1/P2 нет. Финальный safe
suite: 2520 tests + 281 subtests PASS за438,65с, 57 skipped/21 network-paid
deselected, одно прежнее Pillow deprecation warning. Staged sensitive scan
и diff-check PASS.
Private logs/scripts: ../artifacts/repeated-despill-confirmation-20261002/.

## repeated-staged-despill-20261002

Новые данные после отвергнутых способов угадывать foreground/background:
независимый агент и главный агент подтвердили повреждение даже на точно
однотонном фоне. Это отдельный программный дефект, не неоднозначность B.
В staged opaque сначала C=sF+bK решается с отдельной яркостью foreground,
затем поздняя projection снова ищет (1-m)reference+mK, без масштаба яркости.
Немного более тёмный нарисованный край ошибочно принимается за новую примесь.

Точный контроль: K=(0,0,255), core=(240,240,240), F=(225,225,225), a=.6,
C=(135,135,237). Первый solve даёт правильные RGB225/225/225 и alpha.6;
повторная projection с m=.06043, residual15.922≤18 меняет RGB на
239.471/239.471/223.071. Даже excess=0 не спасает от второй projection.
Красная/зелёная перестановки воспроизводят оттенок. В automatic часть таких
пикселей потом восстанавливается, но F210/210/210 становится219/219/208,
а F190/190/95 становится196/196/90. Прежние brightness .7/1 тесты не
попадали в ошибку слабого shade около .95.

Главный агент проследил full native исходники владельца: texture→despill
меняет ≥2 уровня RGB на632/305 visible pixels выбранных ROI уточки/цветка,
медиана изменения19.06/23.70. На цветке виден дополнительный жёлтый кант.
Изменённые пиксели сами по себе не доказывают, что каждый был ошибочен.

Причина → уже восстановленная partial смесь повторно деконтаминируется →
изменение: в opaque_subject пропускать повторный RGB-блок, если 0<a<1,
RGB в [0,255] и max|aF+(1-a)K-C|≤2. Это проверка отсутствия доказательств
второго spill, не доказательство идеального первого матта. При настоящем
additive spill/необъяснённом source или out-of-gamut RGB correction остаётся.
Рассчитывается только выбранная полоса каждого512px tile; edge_ring не
меняется через view. Legacy алгоритм не тронут. Новая alpha-операция не
добавлялась, но последующие RGB-зависимые refinements могут изменить alpha.

Проверка: 12 meaningful ordinary regressions FAIL до правки; после неё
180 related tests PASS за22.09с, включая24 новых ordinary/additive tests
через staged и public automatic на трёх key-цветах. Независимый scratch
guard: 15 ordinary + 6 additive cases, искусственный inconsistent RGB
и156 прежних tests PASS. Исходники владельца не менялись.

Ограничения: старый alpha remap .6→.586108 (153→149) и неизвестный true
foreground остаются; эта правка не заявляет полное удаление цветной каймы,
не подменяет край цветом соседнего материала и не меняет нейромодель.
Actual production full native cutout совпал с диагностическим guard. Два
настоящих cached Clipart NN192→768: 37,56с/39,54с на Linux software Vulkan,
sourceSHA и PNG roundtrip PASS. На dark/white boards дополнительное пожелтение
слабее, но тёмная/цветная кайма остаётся. Native alpha меняется на1034/1088
pixels после следующих refinements; RGBA глубже3px и число visible components
не меняются, visible→zero нет. У цветка3 прежних opaque pixels стали partial,
максимальная alpha loss108; неизвестный истинный matte этих рисунков не
позволяет объявить каждую alpha правильной.
Независимое ревью actual sparse15-line guard: P1/P2 нет; 9 mask controls,
3 known-truth1042×1040 с отверстиями через512px tiles и3 byte-exact legacy
controls PASS. Основной агент проверил скрипт/JSON, индексацию и actual boards.
Финальный общий safe suite: 2520 tests + 281 subtests PASS за438,65с,
57 skipped/21 network-paid deselected, одно прежнее Pillow getdata warning.
Installed Windows/full5016 не проверены; сборка и публикация не выполнялись.
Private scripts/reports: ../artifacts/staged-edge-signal-20261002/,
repeat-despill-guard-20261002/, repeated-despill-neural-20261002/,
repeated-despill-confirmation-20261002/ (включая baseline91bec9d source).

## edge-sharp-preview-20261002

Владелец предпочёл обычный контраст alpha×2 защищённым вариантам со второй
полосой; глобальное автоматическое применение отвергнуто из-за потери тонких
деталей. На2026-10-02 явно согласован отдельный preview инструмента: кнопка
под масштабом, До/После, Отмена/Применить, без настройки силы. Не следует
выдавать этот выбор редактирования за исправление автоматического алгоритма
или цветной каймы. Меняются все промежуточные значения alpha; источник и RGB
не меняются. Для PNG с намеренной полупрозрачностью это тоже изменение,
поэтому никакого автоматического вызова нет.

Решение: proposal хранится отдельно от document.mask/history; Apply коммитит
After даже при показе Before одним undo-патчем. На время preview заблокированы
редактирование, контурные jobs и сохранение. Escape/Undo, смена файла,
возврат/скрытие закрывают только proposal. Проверяется identity/revision
документа; устаревшее предложение не применяется. Геометрия старого контура
после изменения alpha сбрасывается, RGB остаётся исходным.

Риск истории: _trim_history удалит единственный патч, если он превышает64MiB.
Новый apply_mask_proposal проверяет бюджет до изменения mask/history и
атомарно отклоняет неотменяемый шаг. Лимит повтора определяется фактическим
изменением LUT; неподвижная alpha128 также не создаёт пустую историю. Это
предел операции, а не доказательство идеального края.

Проверка:57 focused tests PASS6,23с; actual Qt5016² владельца preview/Apply
изДо/Undo/Redo/Cancel/копия/sourceSHA PASS, RGB/alpha PNG roundtrip exact.
Preview0,753с, save3,751с, peak RSS1028000KiB; Linux Qt offscreen, не Windows.
Независимое ревью: подтверждённых P1/P2 нет,9 дополнительных Qt сценариев PASS,
включая прежнюю Undo/Redo историю, trim/budget failure, focus/keyboard,
stale workers и cache invalidation. Общий safe suite: 2494 tests + 281 subtests
PASS за 437,29с, 57 skipped/21 network-paid deselected; одно прежнее предупреждение
Pillow getdata deprecation. После полного прогона закреплены две проверки
прежней истории и trim/budget в regression tests: 2 PASS, production source
не менялся. Итоговый файл инструмента: 14 tests PASS за 2,35с.
Staged sensitive scan и diff-check PASS; пользовательские PNG и private reports
не включены в коммит, только синтетические approved/actual UI-снимки.
Safe screenshots: docs/ui/3.2/edge-sharp-preview/. Private evidence:
../artifacts/edge-sharp-preview-qa-20261002/actual/verification.json и
../artifacts/edge-colour-and-sharp-preview-20261002/.

## edge-colour-background-ambiguity-20261002

Продолжение offline диагностики после двух проваленных защит сужения.
Трассировка локализовала тёмную кромку в первом staged матте. Измеренный
глобальный blue key(0,2,253); рядом с объектом raw синий бывает228–242.
Предположение → измерить локальный B по заведомо удалённому фону → heldout
проверка подтверждает неоднородность: ошибка B в ближнем слое уменьшается
примерно6,66→3,04 уровня, но значения фона непосредственно под краем неизвестны.

Попытка B-field:11×11 affine fit по alpha0 anchors, отклонение нестабильных
fit/цветов, только partial RGB/alpha, без core/background →1307/820 изменений
у уточки/цветка, улучшение умеренное. Независимый известный эталон, повторённый
главным агентом: наружная полоса B235 заканчивается перед краем, где истинный
B253; все guards и σ≈0,000006 проходят, правильный RGBA100,90,80,76
становится122,108,97,63.14/24 настоящих краевых пикселя повреждены, white MAE
0→7,645. Sweep33/60 ложных изменений, alpha loss до16/255. Хороший fit
наблюдаемого фона не доказывает его продолжение под рисунком. Не внедрено.

Другие проверенные пути:
- Foreground ML, CF trimap и cached U2Net prior дают умеренную разницу, не
  устраняют кант целиком; свободные матты также теряют отдельные положительные
  alpha. Уже установленная библиотека/модель, без скачивания зависимостей.
- Сохранение площади fractional alpha через локальную плоскость улучшает
  ошибку простых эталонов, но на уточке создаёт точки;41/18 видимых и7/4
  непрозрачных эталонных пикселя теряются на кончиках/линиях. Не внедрено.
- Выравнивание тона partial RGB по глубокой opaque опоре →197/31 изменений
  native уточки/цветка → настоящий NN4 на обоих192² фрагментах. Улучшение
  частичное; контроль настоящей тёмной обводки осветляет16 корректных пикселей.
- Native заполнение всего узкого RGB края → настоящий NN4 → новая розовая
  линия у уточки. Classical RGB подмена даёт клетчатость/жёлто-зелёные края;
  более глубокая post-NN подмена затрагивает истинные обводки и создаёт ступени.
  Независимый просмотр подтвердил отбраковку. PostNN nearest4 допустим лишь
  как исследовательская локальная ретушь однородного выбранного участка: часть
  серой жилки уходит, но появляется мелкий крап, на цветке пользу не подтвердили.
  Новую RGB-кнопку на основании такого качества не добавляли.
- Alpha×2 после Photo NN сохраняет тот же RGB, но размытость цвета и меньшая
  детализация остаются; универсальная замена Clipart-модели не обоснована.

Технический итог: не продолжать ослаблять guards или автоматически брать цвет
соседнего материала. Для спорной полосы требуется намерение пользователя или
более надёжный исходник. Выбранная явная alpha-кнопка выше не является RGB-fix.
Вся alpha и sourceRGB preservation метрика проверяет сохранность данных, но не
правильность неизвестного foreground. Прототипы вне Git, воспроизводимые
скрипты/JSON: ../artifacts/edge-colour-and-sharp-preview-20261002/;
real boards в native-boundary-fill-edge-20261002, local-edge-rebuild-20261002,
classical-colour-boundary-20261002, weighted-boundary-retouch-20261002,
neural-rim-tone-edge-20261002, photo-sharp-edge-20261002 в том же artifacts.
Full NN5016, Windows и исходный chroma-медвежонок недоступны. Источники,
сервер/лицензии/версии/релизы не менялись; сборка/paid calls не выполнялись.

## opaque-edge-protection-followup-20261002

Цель: внешний вид обычного сужения ×2 без потери нарисованных деталей,
паразитного цвета и второй полоски. Только offline QA на отдельной ветке.

Попытка 1: локальная ширина маски определяет, где применять ×2 → защита
узких деталей по distance-transform → 420 штрихов без потери непрозрачных
пикселей, но отдельная линия рядом с телом заимствует его ширину; независимый
контекстный контрпример удаляет 76 непрозрачных пикселей. Не внедрено.

Попытка 2: дополнительно защитить локальные гребни частичной alpha →
420 штрихов и первые контекстные случаи проходят по отсутствию непрозрачной
потери → расширенные 3360 повёрнутых сцен обнаружили один случай потери
60 непрозрачных пикселей, 315 выборок непрозрачной средней линии исчезли.
Главный агент прочитал независимый сценарий и повторил точный случай:
поворот90°, зазор0,75 и ширина0,25 исходного пикселя. Нативная alpha
`255,255,255,80,16,0,0` монотонна: уменьшение уже смешало тело, зазор
и линию. Гребня нет, поэтому защита не отличает линию от размытия тела.
Также результат содержит `...16,0,0,0,2,4,4,2,0,0`: появилась вторая
слабая полоса после прозрачного промежутка. Владелец независимо заметил
внешнюю линию и предпочёл обычное ×2. Подготовленные изменения main.py
и native_alpha.py отменены; source не изменён. После двух неудачных попыток
новые детекторы ширины не добавлялись, исследование сменило подход.

Неослабляющий вариант меняет только верхнюю половину alpha. На трёх эталонах
MAE2,143/2,717/4,968 →1,594/2,076/4,590 без потери, но слабый внешний
переход остаётся, визуальная цель не достигнута. Восстановление всей частичной
полосы нативным RGB даёт ступенчатый/зелёный край; ограниченная замена
737/1511 пикселей недостаточно улучшает результат. Оба не внедрены.

Настоящие дополнительные локальные нейропрогоны на тех же192² фрагментах:
Animevideo4 мягче и теряет детали; Photo4 до удаления фона даёт цветные
тонкие полосы у уточки и точки/мягкость лепестков у цветка. Копии входов
сверены SHA до/после, выход768². Software Vulkan не доказывает скорость
Windows/GPU или качество полного5016² результата.

Маттинг по двум фонам: nativeRGBA композитится на чёрном/белом, оба RGB
реально увеличиваются Clipart4. Формула alpha=1-median((white-black)/255)
правильна для общего F/alpha, но нелинейная сеть этого не гарантирует.
На уточке/цветке p95 расхождения оценок alpha по каналам0,196/0,314;
p95 ошибки повторного RGB-композитинга26/37 уровней. Свободный результат
ослабляет19882/55233 исходно непрозрачных пикселей, из них543/1129 ниже240;
минимумы165/170. Теряется198/259 исходно положительных пикселей.
Граница резкая, но полые тонкие полоски остаются. Защита тела не доказывает
правильность оставшегося края. Независимый просмотр и математическое ревью
подтвердили ограничение; unrestricted-замена исключена.

Отдельный настоящий нейротест на эталоне с известным непрозрачным телом
и соседней линией: BILINEAR MAE2,098, обычное×2 1,210 с80 потерянными
непрозрачными пикселями; двойной маттинг1,573 без alpha0 на эталоне, но
медианная alpha линии падает56→1/255. На белом фоне кремовый RGB с alpha1
практически исчезает. Проверять лишь alpha>0 недостаточно.

Ограниченная RGB-only версия использует согласие двух результатов, диапазон
цвета и малую ошибку композитинга; меняет3665/5649 частичных пикселей.
Вся alpha, непрозрачное тело и прозрачный фон побайтно неизменны, но полосы
недостаточно исправлены; пороги диагностические, не калиброванные. Это не
подтверждённое исправление качества и не готовая архитектура двойного upscale.

Трассировка исходной1254² уточки: проблемный тёмный край виден уже в
staged_result. В выбранном ROI последующие стадии меняют0/0/22/0/234/8/14
пикселей; нейроувеличение затем подчёркивает тонкие полосы. Для ряда пикселей
модель линейной смеси с ближайшим цветом тела не имеет малой ошибки:
нельзя просто ослабить проверку и перекрасить край в соседний кремовый цвет.
Фактический measured key(0,2,253), исходный SHA после трассировки совпал.
Дальнейшая диагностика должна разобраться с цветом первого staged-края,
а не обещать исправление одной настройкой alpha.

Сценарии и JSON сохранены вне Git в ../artifacts/opaque-edge-followup-20261002/;
PNG/отчёты в protected-edge-20261002, protected-ridges-20261002,
non-erasing-edge-20261002, native-edge-colour-20261002,
bounded-edge-colour-20261002, animevideo4x-edge-20261002,
photo-before-key-20261002, dual-matte-edge-20261002,
dual-colour-only-20261002, native-duck-stages-20261002.
Production, пользовательские источники, сервер, релизы и лицензии не меняли;
сборка/платные операции/загрузки не выполнялись. Качество остаётся нерешённым.

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


## upscale-order-comparison-20261002

Владелец поручил проверить увеличение до удаления фона и выбрать качественный
вариант. Исходники и production не менять без результата сравнения. В /tmp уже
есть официальный Linux NCNN runtime/models; первый32px probe exit255:
vkCreateInstance failed -9/invalid gpu device. CPU gpu-id=-1 в этом бинарнике
также недоступен. Причина: системный Vulkan driver отсутствует, не модель/PNG.
Обнаружен ранее скачанный /tmp/clipart-vulkan/runtime software driver; только
для дочернего процесса заданы VK_ICD_FILENAMES/LD_LIBRARY_PATH. Повторный32px
neural probe real realesrgan-x4plus-anime ×4 PASS. Ничего не установлено/скачано,
сервер/лицензии/платные APIs не используются. Actual192px context crop проверяется
двумя порядками; не выдавать его за полный5016 PNG или Windows acceptance.


Actual cropped comparison completed:2owner192² context inputs→768²,2orders
sameClipart realesrgan-x4plus-anime×4;2Photo realesrgan-x4plus×4;1Clipart
realesr-animevideov3×2. Всего7real neural outputs. Первый cropped final removal
после NN FAILED ChromaKeyAmbiguousError: crop пересекал object, разные side
medians. Это диагностическая потеря full-background context, не доказанный
product defect. Данные: originalsource имеетblue borders; actualcropодинside
представленforeground. Диагностическое решение32px sourceblue frame вне768²
crop, затем убратьframe; neural crop pixels не менялись. Повторный keyer PASS.
Не ослаблять product uniform-background guard на основании этого crop.

На duck upscaling-first усиливает green/magenta sharp strokes; flower становится
чётче, но colour outlines на мелких выступах остаются. На обоих Photo сохраняет
акварельную фактуру лучше Clipart с компромиссом softdetail; Clipart яснее по
жилкам/контурам. Ordinary bilinear мягче, hybridRGBA+alphaB сильныештрихи не решает.
Видимая kayma duck остаётся даже Photo: не обещать perfectcutout. Independent
review совпал с выводом по стилю и отсутствиеuniversalorderwinner.

Photo/Clipart alpha EXACT forboth768² и EXACT inputalphaBILINEAR. ×2 result384²
RGBA alpha EXACT inputalphaBILINEAR. Actual rawcropbytes matchoriginal source;
оба fulloriginalSHA before/after flower-verification exact. Для первоначального
standalonefinisher не сохранялся beforeSHA: его booleanне использовать как
доказательство, заменён пояснением; итоговый before/after proof независимый.
Evidence ../artifacts/upscale-order-20261002/final-verification.json, boards,
/tmp/upscale-order-final-verification.log. Pure software timing101/105Photo,
30..48Clipart×4/9.87Clipart×2: не controlledbenchmark, GPU/Windows speed unknown.
Production source/defaults unchanged7677ded; tests не повторялись без codechange.
Full1254→5016 neural/installed Windows quality остаётся непроверенным. Рекомендация
remove→Photo×4 относится к фактуре показанной акварели, не к идеальной маске/всемстилям.


## opaque-painted-edge-width-20261002

Владелец уточнил: рисованные перья, шерсть и иголки должны быть непрозрачными.
Диагностика выполнялась без изменения программы. Для двух ранее полученных
реальных нейроувеличений сохранены четыре варианта alpha: исходная, сужение
перехода ×2/×4, жёсткий порог 128. RGB во всех вариантах побайтно сохранён,
PNG после открытия совпали, хеши диагностических входов до и после совпали.
На эталонных острых выступах сужение ×2 удаляет четыре истинно непрозрачных
пикселя, ×4 пятнадцать, порог 53. На тонких линиях ×4 удаляет 204 непрозрачных
пикселя, порог 420. Меньшая средняя ошибка alpha не доказывает сохранность деталей.
Эти варианты не внедрены; пользовательские реальные маски не имеют идеального эталона.

Монотонная кубическая интерполяция без отрицательных выбросов дала умеренное
улучшение, но проверка обнаружила зависимость от порядка осей: максимальное
различие alpha 15. В 60 пробах появились 43 положительных пикселя вне округлённой
BILINEAR-маски. Исправление только диагностического прототипа: усреднить оба
порядка осей и сохранить нули/255 обеих базовых интерполяций. Первый симметричный
вариант с одним базовым порядком не прошёл проверку: округление самой Pillow
BILINEAR также зависит от порядка. После защиты по обоим порядкам 20 проб на
случайных, слабых и одномерных масках дали точную симметрию и отсутствие новых
пикселей вне базовой поддержки. Не выдавать первый вариант за безопасный.

Независимая проверка итогового прототипа: 420 непрозрачных штрихов, 12 направлений,
ширина 0,125–2 исходных пикселя, пять положений относительно сетки. Ошибка alpha
ниже BILINEAR во всех случаях; истинные видимые/непрозрачные пиксели не удалены,
маски связны, проверенные точки средней линии видимы. Но непрозрачность не
восстановлена: минимальная alpha истинно непрозрачного пикселя 28; 22 из 109788
таких пикселей чуть слабее исходной BILINEAR. На трёх основных эталонах MAE
2,143/2,717/4,968 → 1,617/2,100/3,843, без удалённых эталонных пикселей.
Проверки геометрии не доказывают восстановление исходного цвета реального объекта.

На реальных фрагментах окончательный вариант удаляет 790/977 слабых пикселей
относительно BILINEAR; идеальной маски нет, поэтому не называть их все мусором.
Независимое визуальное ревью: переход немного уже, кончики сохраняются,
остаточная цветная полоска видна и на белом фоне. Только изменение alpha её
не устраняет. Намеренная полупрозрачность загруженных PNG не должна попадать
под такую коррекцию; нужен подтверждённый контекст конкретного изображения,
а не один provider или result_kind. Универсальная замена не обоснована.

Полная alpha-маска 5016 × 5016 рассчитана за 1,022 с, peak RSS процесса 318164 KiB;
PNG сохранён и открыт побайтно, входная диагностическая копия неизменна. Это не
полное нейроувеличение, не бюджет всего WorkerThread и не Windows-приёмка.
Материалы: ../artifacts/opaque-edge-width-20261002/symmetric-verification.json,
full-symmetric-verification.json и реальные dark/white сравнения. Сценарии
/tmp/compare_opaque_edge_width.py, /tmp/monotone_alpha_symmetric.py;
это диагностические прототипы, не исправления production.

Главный агент прочитал независимый сценарий и повторил все 420 случаев в
/tmp/vibix32-venv: итоги совпали. JSON сохранён как
../artifacts/opaque-edge-width-20261002/strokes-420-root-verification.json.
Копии диагностических сценариев сохранены рядом с доказательствами вне Git.

remaining-edge-20261003 continuation: two realNN context probes at exactalpha: flower280480 improves239195185→226223221; duck265340 worsens176153162→135116146. Opaquedonor variant rejected, localstrong-donor variant not started: full disk. Product exactv16.
Disk193GB/0free: only own regenerateable NN inputs and completed pytest-564/565/566 temporary fixtures removed, savedreports/inputs/models intact;5MB vanished again. Agent readonly trace auto-review deadline timeout, ordinary readonly path later worked. Await owner for old /tmp/vibix-size-audit/extracted1.5GB cleanup, not deleted.
Spatialveto candidate improvesdarkpoint but distinct9x9paintmarker negative fails: notaccepted. Precise rawmatte misestimates variableGT coverage; localphysicalfit prototype3keys maxerror1. Need pigmentsupportnegatives and permanentRED before adoption; no newproduct edit.


## artifact-download-20261006

Первая gh run download передачи Windows3.2.12 артефакта завершилась SIGTERM143 без сохранённого файла. Причина прекращения процесса неизвестна; сборкаGitHubrun37490182834 при этом SUCCESS, artifact11425258051 доступен. Проверены доступность и82GB free space. Изменена только доставка: gh api artifact/zip пишет поток в новый .part. Повторная передача exit0,242819696bytes; ZIPCRC PASS, installer SHA совпала с checksum/provenance, версия3.2.12 иsource438a665 подтверждены. Новая сборка/настройки приложения не требовались. Evidence: ../artifacts/studio-3.2.12-chroma-beta-20261006/installer-verification.json.


## composer-results-crash-20261006

Симптом владельца: Studio закрылась при выборе одного из7готовых промптов слева,
до этого параметры заполнены частично. Первый реальный QTest.mouseClick по
строке1 на default draft (толькоsubject) воспроизвёл SIGSEGV/139. Источник не в
нехватке данных: генерация успешно вернула7вариантов, падение началось в click.

Причина: currentRowChanged → _select_variant → _render → QScrollArea.setWidget
синхронно удаляет предыдущий body вместе с emitting QListWidget, пока нативный
Qt mouse/key handler ещё использует этот widget. Прямые вызовы _select_variant
в прежних тестах не проверяли этот lifecycle и не выявляли native crash.

Попытка1: перед setWidget отделить старый body через takeWidget, hide/deleteLater.
Проверка: исходный15clicks+actions repro PASS; связанные51tests+2subtests PASS,
полный Composer77tests+2subtests PASS. Независимая DeferredDelete-проверка
подтвердила освобождение body/list, но нашла потерю keyboard focus после первого
Down. Это отдельный UX дефект: новый список не получает фокус прежнего.

Доработка по данным ревью: _select_variant восстанавливает фокус нового списка
только если прежний список был сфокусирован. Регрессия использует Down/Down/Up/
End/Home через настоящий app.focusWidget без повторного setFocus. Добавлено
sendPostedEvents(DeferredDelete) и sip.isdeleted старого списка после завершения
mouse event. Minimal/enriched/AI proposal и временный подписанный модуль
проверяются в отдельных процессах, чтобы native crash не завершал весь pytest.
Итоговые результаты и delivery status ведутся в STATE.md; production и paid
операции этим исследованием не выполнялись.


## composer-full-review-20261006

По поручению пользователя отдельный readonly reviewer и root независимо
воспроизвели3существовавшихP2. Попыток исправления пока нет, выпуск отложен.
1. QTextEdit(current) распознаёт HTML: Edit/Save без изменений теряет literal
   <lora:…>. Причина и проверка: plain-text-probe.log.
2. Save snapshot берётся до modal exec; поздний перевод создаёт edit во время
   диалога, после записи старого snapshot pop() удаляет новый edit и снимает dirty.
   Real Qt/SQLite подтверждают потерю: save-race-probe.log.
3. Field translation сравнивает только source; новый ручной target до ответа
   затирается setText. Независимые пробы: field-race-probe.log.
Evidence в ../artifacts/composer-full-review-20261006/. Root close/cancel/late
callbacks3/3PASS; paid/network/production не использовались. Требования, статус
и следующий шаг ведутся в STATE.md, без объявления findings устранёнными.


### Исправление composer-full-review-20261006, разрешено владельцем

HTML parsing → пустой QTextEdit + setPlainText → literal LoRA/HTML/angle-bracket
roundtrip3cases PASS. Save race → свежий content snapshot после Save и replace
confirmation; guard identities выбранной карточки/proposal/record → actual modal
QTimer callback сохраняется в SQLite и UI, cancel сохраняет edit, replace
сохраняет late translation и othercard edits; arrival нового AIproposal отменяет
устаревшее сохранение без потери proposal. Target overwrite → capture target
перед запросом, apply только при неизменных source+target и видимом editor;
конфликтный/закрытый/deleted editor показывает перевод отдельно для копирования,
через существующий readonly dialog.5cases + literal readonly result PASS.
Production исправления ограничены тем же module ui.py, без изменения Core.
Первый regression subset23PASS; полный Composer90PASS+2subtests9.72s. Оппонент
независимо повторил исходные3сценария с реальными Qt/SQLite:PASS, новых findings0.
Evidence: ../artifacts/composer-data-loss-fixes-20261006/. Windows/real provider и
публикация модуля не выполнялись, доступ пользователя ещё на старом модуле.

## editor-file-list-height-20261006

Причина: ClipartTransparencyEditorPage._set_tool('pen') вызывал
files_frame.setFixedHeight(90). Кисть снимала ограничение; перо всегда возвращало
90px, независимо от завершения обводки. Старый UI-тест закреплял этот размер
и не проверял удобство списка.

Воспроизведение: усиленный regression с21строкой и реальными mouseclicks
brush/pen/brush/pen упал до исправления: viewport52px против нужных пяти строк
по26px. Изменение: удалены5строк условного ограничения высоты, исходное
распределение файлов/прокручиваемых инструментов2:3 сохранено.
Проверка того же сценария PASS;63связанных tests PASS8.04s. Styled captures:
1120×780 files296px в обоих режимах,980×700264px, возврат296px.
Изменения исходных изображений/alpha/алгоритма отсутствуют. Windows/device и
production release пока не проверены; код редактора принадлежит Core Studio.

## one-pixel-brush-20261007

До изменения1pxнельзя было получить добавлением кнопки: diameter//2 даётradius0,
background_mask отклонялradius<1, а keyboard искалradius*2 в списке диаметров.
Решение: radius0явно означает1×1opaque stamp, отрицательные radius отклоняются;
keyboard использует выбранную кнопку; видимый cursor minimum radius0.5. Для3px
используется прежнийradius1; все6–64неизменны. Проверены1pxadd/remove на4hardness,
continuous stroke, реальные клики при50/100/300%,undo/redo/save RGB и3pxbbox.

Первый новый save-тест ошибочно требовал неизменность обработанногоoutput-файла
послеSave: текущий договор сохраняет output in place. Исправлен толькоfixture/assertion:
unchanged source доSave, saved RGB сравнивается с исходнымиbytes, saved alpha смаской.
Производственный save-код не менялся. Итог88tests+15subtests PASS9.28s,
UI geometry1120×780/980×700 PASS. Windows/build/publish пока не выполнялись.

## editor-immediate-sharpen-20261007

Прежняя схема намеренно предлагала edge contrast preview с отдельным Apply.
Владелец признал лишние подтверждения неудобными и утвердил immediate single
step+existing Undo/Redo. sharpen_edge теперь синхронно считает прежнийLUT,
коммитит через apply_mask_proposal и сбрасывает устаревший векторный контур.
Preview-only state/signals/UI/guards удалены; busy/manual/local-edit guards и
history-memory rejection сохранены. Fixed points0/128/255 останавливают повтор.

Первый новый набор выявил3ошибочных допущения тестов: скрытые До/После относятся
к contour-local preview, а при switch/reload прежняя реализация восстанавливает
маску-черновик без raster undo stacks. Проверки уточнены под утверждённый scope,
поведение history между файлами не расширялось. Immediate per-file history,
source/RGB/save, limit/Undo-reenable/Redo-disable и budget rollback проверены.
Связанный набор105tests+15subtests PASS11.49s; UI captures и diff checkPASS.
Windows/build/publish ещё не выполнялись. Independent review0findings,
57tests+15subtests PASS6.82s;40baseline brush comparisons и local/doc-mismatch guardsPASS.


## Шесть размеров: устаревшее ожидание native smoke,2026-10-07

Windowsrun37579012511 остановлен на двух packaged entrypoint tests.
Причина: studio_contour_smoke после default16 и Minus проверял radius5
(10px), удалённый по утверждённому ряду1/3/6/16/32/64. Локально оба теста
воспроизведены FAIL до исправления. Изменено только ожидаемое поведение:
radius3 и selected6px послеMinus. Проверки маски, Undo/Redo, RGB, исходника
и сохранения не ослаблены. После исправления166tests+29subtestsPASS,1deselected;
повторный Windowsrun37579444354SUCCESS, installedCore13/13PASS.
Подробности выпуска и evidence см. STATE.md.
Первый запуск не создал установщик; PRIVATE восстановлен, публикации не было.


## Автоконтур: незаметный ход расчёта,2026-10-07

Владелец сообщил отсутствие заметного отклика и повторные клики.
Диагностика до правок: worker уже асинхронный; статус QLabel расположен
в прокручиваемой панели, indeterminate animation отсутствует; активная
кнопка Автоконтур превращается в Отменить. RealQt delayedFuture probe
подтвердил busy=true и enabled Отменить. В1120×780 label был виден,
поэтому скрытость при любом размере не утверждается. Повторный клик
по существующему handler при busy вызывает cancel_contour.
Предложено вынести feedback наверх и отмену в отдельную кнопку.
Исправлений источников/сборок ещё нет; статус и макеты в STATE.md.


## Сглаживание: готовыйAA и тонкие штрихи,2026-10-07

Независимое pure review: первый inward-AA кандидат уменьшал alpha17pixels
готовогоAA-круга (MAE.00606→.03445), 1px diagonal масса−20.4%, isolated255→159.
Два независимых контроля воспроизведеныFAIL до правки. Изменение: затрагивать
толькоalpha255, безfractionalalpha в3×3окрестности, solid support>=4. Это
защищает existingAA и sparse1px strokes, не раскрываяalpha0.25puretestsPASS
после правки, включая arc handles/tile seams/cancel/scope. Предыдущие результаты
не переписаны: artifacts/editor-shared-edge-20261007/; защищённый кандидат
в protected-aa/. Итоговый status/evidence находятся в STATE.md.


## Shared edge: scope history и lifetime,2026-10-07

Review до выпуска обнаружило: обычный rasterUndo сбрасывает guide/selection;
no-op set удерживал старые документы и геометрию. Edge history отмечается
отдельно, только его Undo/Redo сохраняют чистый guide; обычная brush history
не меняется. Обаcache ограничены текущей геометрией/выделением, edge также
doc/revision. Регрессии selectedUndoRedo и document cache release PASS.
Итоговый read-onlyreview0open findings; cancel-before-submit/stale-selection
независимыеQtprobesPASS. Autocontourfeedback исправлен: bottom-image-only
indeterminate strip, отдельнаяCancel, повторныйstartignored, busy доcopy
и до конца commit; vector transform теперь worker. Длительные операции
проверены delayed workers, errors/cancel не публикуют mask/history.


## composer-ai-failure-opacity-20261007

Владелец: «Предложить с AI» не выполнилось, выбранKIE/Gemini3.8Flash,
вконце сообщалось возможносписание. DiagnosticZIP содержит25eventsStudio3.2.16,
открытиеComposer есть, сами AIevents отсутствуют. Нельзя установить конкретный
ответпровайдера или фактсписания.

Причина утраты информации подтверждена кодом/контролями: perform_request ловит
HTTP/network/parse/validation пододнимTextGenerationError; ComposerJob._run
снова заменяет любые Exception общимсообщением. Три независимыхmockedконтроля:
HTTP401, HTTP200сKIEbusinesscode402 и finish_reason=length дают одинтекст.
requests.post подменён, network/paidrequests0. KIEдокументация подтверждает
ошибкивHTTP200 body(code/msg), которые нужноразбиратьдочтенияchoices/candidates:
https://docs.kie.ai/42969115e0 . Это defect observability, не доказанная причина
пользовательского отказа. До правки evidence: ../artifacts/composer-ai-scene-20261007/.


Исправление composer-ai-failure-opacity-20261007: введён ComposerAIError с
фиксированными сообщениями и ограниченными числовыми кодами. HTTP, KIE code
в HTTP 200, таймаут, сеть, усечённый JSON, отказ и нарушение контракта различаются.
ComposerJob доставляет эти сообщения, неизвестные исключения по-прежнему скрыты.
Host записывает безопасные события начала/исхода с correlation id, провайдером,
моделью и категорией. Ключ, промпт, raw response и произвольный exception не пишутся.
Лимит токенов/число запросов не увеличены; RU/EN/семь вариантов/защищённые поля
проверяются прежним строгим валидатором. After-контроли дают три разные причины,
каждый с одним подменённым POST; before-контроли сохранены отдельно.

Независимое ревью нашло два P2: checkable-кнопка меняла вид до отказа manual guard;
native KIE functionCall попадал в категорию json. Отказ смены режима теперь
перерисовывает прежний режим; functionCall классифицируется как refused.
Реальный QTest click + отмена диалога проверен на Шаблонах и Сцене, отдельный
native-response контроль PASS. При написании теста журнала ошибочно ожидался
прямой порядок read_events: он обратный по контракту; тест сортирует sequence,
поведение журнала не менялось. Финальные 159 tests + 2 subtests PASS; повторное
read-only ревью: 36 PASS, открытых существенных замечаний нет.
Исходный отказ на реальном KIE не воспроизведён: raw response отсутствует.


## composer-directions-20261007

До реализации apply_template заменял незакреплённого героя примером рецепта.
Новые reusable-сцены должны сохранять собственный объект, профиль и identity.
Выделены совместимые группы типов; несовместимый сценарий отклоняется атомарно.
Нейтральный пример отслеживается только в текущей странице; запись не меняет
схему черновика. Маркер сбрасывается после пользовательских identity-правок,
смены типа/профиля и открытия сохранённой записи/AI-черновика. Собственные
референсы и закреплённый герой запрещают замену даже нейтрального примера.

Независимое ревью и контрольные прогоны выявили/подтвердили:
1. Общие pools превращали UGC в macro/portrait lens; image-рецепт терял руки,
   человека или приготовление, если смысл был только в изменяемом shot/style.
   Исправление: сохранять captured action в image; метаданные относительных
   вариантов по уникальной bilingual style signature+mode. Style/camera/action
   сохраняются, меняются композиция/ракурс/заполняющий свет. No implicit locks.
   Все 48 сцен → по 7 уникальных RU/EN вариантов с сохранением смысловых полей PASS.
2. Первый маркер нейтрального примера разрешал только предмет/object и блокировал
   people→products без пользовательского ввода. После введения provenance marker
   этот переход PASS. Дополнительный профиль/appearance контроль показал, что
   маркер надо сбрасывать при любых успешных identity-правках/выборе профиля.
   Точечный сброс исправлен; 4 identity-fields, профиль, несовместимый custom герой,
   ручная отмена и декоративная правка проверены, исходный draft не повреждается.
3. Легальный shot 600 символов после суффикса превышал model limit, хотя результат
   назывался complete. Общий FIELD_TEXT_LIMIT=600 использован в валидаторе и
   фильтре кандидатов; текст не обрезается. Max-length одного/трёх полей → все
   возвращённые варианты валидны; недостаток сочетаний явно insufficient.
4. Пересборка сохранённого варианта давала left+right/left+left. Перед построением
   альтернатив теперь снимаются только известные парные RU/EN terminal suffixes;
   current остаётся вариантом, новые поправки заменяют старые. Проверки <=1поправки
   на ось в обоих языках и exact locked-angle PASS. Последний finding закрыт
   независимым повторным ревью, 2 tests PASS.

Финальный общий набор: 235 tests + 2 subtests PASS, 14.54s. Целевой 93 PASS,
включая signed-module runtime. UI в 12 состояниях/библиотеке/сохранённом объекте
проверен Linux Qt 1120×780; снимки в docs/ui/3.1/composer-directions-20261007/.
Платных запросов и Windows-сборки не было. Пользовательские файлы и старые ID
шаблонов не удалялись. Статус по требованиям в STATE.md, без повторения истории.


## Первый шаг конструктора: дублирующая и неоднозначная навигация, 2026-10-08

Нижняя «Сохранённые» была общей previous-кнопкой на шаге0, повторяя верхнюю
вкладку. «Начать с нуля» вызывала goto_step(1), ничего не очищая; «Далее» делала
тот же переход. По одобренному предложению первые две кнопки убраны, а «Далее»
на шаге0 переименована в «Настроить самостоятельно». Переход сохраняет draft.
Дополнительно реализовано одобренное визуальное разделение Тип/Сценарий.

80 tests + 2 subtests PASS (9.55s), включая signed-runtime и реальные result
clicks. Qt probe проверил 12 состояний, setup/back/library, exact draft values.
Первый probe находил старую скрытую nextButton, ожидающую DeferredDelete, и упал
на тексте; исправлена только последовательность обработки событий probe.
Повторный probe PASS; поведение удаления widgets приложения не менялось.
Снимки и navigation-checks-20261008.json в docs/ui/3.1/composer-directions-20261007/.

Последующее уточнение владельца: действие «Далее» должно оставаться навигацией,
а способ начала выбирается отдельно. После показа двух новых макетов введены
По шаблону/Самостоятельно и отложенное применение карточки по переходу дальше.
Повторные переключатели режима и его заголовок убраны по отдельному уточнению.
Проверены отмена manual guard без изменения draft, сброс pending при смене
режима/категории/способа, сохранение профиля/закреплений и отсутствие повторного
применения при возвращении. 241 tests + 2 subtests PASS; 16 actual Qt состояний
PASS, start-paths-actual-checks-20261008.json. Независимое ревью замечаний не нашло.

## Выравнивание кнопок способа начала и режима, 2026-10-08

Причина: верхний QHBoxLayout центрировал пару кнопок вместе с подписью
«Начать:», нижний центрировал только кнопки. Поэтому верхняя пара была сдвинута.
Удалена лишняя подпись, обе строки теперь используют одинаковую геометрию.
Actual Qt 1120×780: в 4 сочетаниях способа/режима x и размеры соответствующих
кнопок совпадают точно (190×38). 36 UI tests PASS, 3.36s; снимок просмотрен.
Evidence: docs/ui/3.1/composer-directions-20261007/aligned-start-checks-20261008.json
и actual-aligned-start-*-20261008.png. Windows-сборка не выполнялась.

## Вложенные сценарии: несовместимое наследование камеры и описаний, 2026-10-08

Независимое семантическое ревью до приёмки нашло четыре дефекта новых данных:
1. Наследование camera/angle/lighting от базовой сцены противоречило новым
   действиям: камера двигалась в action при locked camera; natural trail получал
   street/facades; flatlay и 3/4 или table-height и overhead сосуществовали.
2. Сценарий игрушки требовал paw, хотя тип животных не ограничен лапами.
3. «Способ использования» каталога только поворачивал товар для масштаба.
4. В товарном Lifestyle рука «устраивалась удобнее», ошибочный actor в RU/EN.

Причина: совместимый базовый жанр не гарантирует совместимость отдельных
параметров нового сценария; короткие данные не проверялись как полный prompt.
Исправлены конкретные данные: движение камеры отдельно в camera_reels,
действие описывает объект; angle и lighting согласованы с выбранным планом
и сценой, несовместимые defaults не наследуются. Игрушка касается естественным
для животного способом; товар используется по назначению; actor отдыха человек.
Детали природы обобщены, чтобы не подменять пользовательский объект листом/водой.
Явные стабильные ID записаны в данных вместо вычисления из порядка карточек.

Проверка после правки: 6 новых семантических/совместимых регрессий PASS;
36 tests UI/nested/runtime PASS (12.33s), затем общий набор501 +2subtests PASS
(69.96s). Повторное read-only семантическое ревью закрыло все4 finding,
серьёзных новых противоречий не обнаружено. Exact hashes всех69 прежних recipes
совпали, каждый старый ID применим. Actual Qt70 состояний,1120×780 PASS;
реальные изображения/видео не генерировались, качество моделей не оценивалось.
Текущий статус и ссылки на evidence в STATE.md.

## Beta3.2.17: версия gh не поддерживает флаг visibility, 2026-10-08

Первый orchestration отказал до build dispatch: установленный gh2.45.0 не знает
--accept-visibility-change-consequences. Та же команда в finally не прошла;
независимый gh repo view подтвердил фактический PRIVATE, исходная видимость не
менялась. Причина проверена gh --version/gh repo edit --help, без слепого повтора.
Внешний artifact script переведён на gh api PATCH repos/... с private boolean,
с обязательным view после возврата. Первая запись сохранена отдельно; новый
запуск проверяется по итоговому run/source/privacy evidence. Исходники приложения
и workflow для этого отказа не менялись. Текущий статус в STATE.md.

## Beta3.2.17 Mac: порядок аргументов lipo, 2026-10-08

Первый native ARM job113129760303/run37721439647 прошёл тесты, SHA скачанного
апскейлера совпал, но lipo отклонил проверку архитектуры. Полный job log сохранён
в evidence выпуска: unknown architecture specification flag у имени бинарника.
Причина: lipo -verify_arch принимает список архитектур до конца аргументов;
имя входного файла должно стоять перед командой, иначе считается архитектурой.
Исправлены оба вызова на lipo <binary> -verify_arch <arch>. Добавлена проверка
конфигурации против прежнего порядка. Для отдельного повтора Mac добавлен
build_windows(defaulttrue), чтобы не повторять незатронутую Windows-сборку.
Источник приложения и подписанные payload не менялись. После новой проверки
конфигурации выполняется native Mac build; результат в STATE.md.

После исправления lipo native Mac run37722280070 SUCCESS (ARM/Intel). Оба готовых
приложения и распакованные ZIP прошли frozen Core13/13; локальный audit ZIP CRC,
SHA/provenance/version/Mach-O architecture PASS. Windows job113129760042 SUCCESS.
GitHubPRIVATE подтверждён отдельно. Текущий итог публикации в STATE.md.

## Beta3.2.17: сервер не разрешал Mac Intel, 2026-10-08

До stage обнаружено: deployed Postgres create_release whitelist не включал
macos-x64, хотя ZIP transport и клиент уже поддерживали Intel. Рабочих данных
до исправления не меняли. Поддержка добавлена в отдельной server branch81e5003,
Memory/Postgres и admin ZIP selector. Полные215tests на отдельной PostgreSQL и
Chrome6states PASS; read-only review без findings; offline образ развёрнут с
backup/rollback, без migrations/изменения прав/config/key. Подробная история
в ../license-macos-beta-worktree/docs/ERRORS.md, текущий статус в STATE.md.


## composer-results-20261008

Владелец: после Предложить сAI в beta3.2.17 ошибка категорииjson.
Ответ провайдера отсутствует, конкретная причина пользовательского отказа неизвестна.
Нельзя считать текст ошибки доказательством усечения или списания.

Подтверждён отдельный дефект: parse_composer_response выполняет json.loads
непосредственно над content. Контроль исходногоHEAD4912af9: полный объект
в ```json блоке отвергнут сcode=json. Исправление: снять только единственный
полный внешний Markdown-блок, затем обычныйJSON parse и прежняя strict
проверка7вариантов/RU/EN/locks/exclusions. Произвольный текст вокруг,
несколько блоков и повреждённыйJSON не восстанавливаются. ДляKIE явно
stream=False/include_thoughts=False, убран повтор той же схемы в system message;
документация https://docs.kie.ai/42969115e0 описывает эти параметры.
Не добавлены запросы, повторы, лимиты, зависимости или логирование content.

При первой проверке нового async-теста дваFAIL были вызваны его выбором другой
карточки перед quote callback: это штатно меняет revision и отменяет отправку.
Тест заменён сменой языка, не меняющей snapshot; четыре outcomes PASS.
ActualQt снимок выявил обновление скрытых старых кнопок вместо текущих из-за
findChild до deleteLater. Изменение: искать translate только в текущем body,
AI только в текущем footer. Новые assertions проверяют эти реальные controls.
84tests+2subtests PASS9.75s; actualQt1120×780 results.png/ai-wait.png.
ПользовательскийAI-сбой требует diagnosticZIP после ошибки/реального запроса;
платных запросов не выполняли, ключ на сервере недоступен. UI исправления
и подтверждённый parser defect завершены, весь live сценарий не подтверждён.

Дополнительно24 существующих diagnostics tests PASS0.63s: категории ошибок,
усечение/отказ, безопасный журнал. Итого108tests+2subtestsPASS.


## studio-navigation-20261008

Владелец: верхние действия отличаются между модулями, последние проекты занимают
много места, Все проекты показывает многочисленные одинаковые Без названия.
Причина подтверждена исходниками: ModeSelectionScreen рисовал4служебные кнопки,
AppShell толькоAPI/диагностику, Composer отдельныйbrand/settings; домашний экран
рисовал3карточки, _show_all_projects использовал толькоrecord.name.
Изменение: одна Core-панель внеstack; module navigation сохранена, дубли скрыты,
canvas_focus_changed управляет временным скрытием общей панели. Вместо карточек
одна кнопка/полныйdropdown; label из module catalog/name/local updated_at.
Сохранённая модель/данные не менялись, menu actions адресуют прежний project_id.
Проверка:53tests+11subtests PASS26.24s;24 новыхtests PASS8.73s, включая signed
Composer,18labels,20IDs,focus и4callbacks. ActualQt снимки в
 docs/ui/3.1/studio-navigation-20261008/. Платных запросов/сборок0.

Дополнительно62 module-update UI/auto-clipart workflow tests PASS96.45s;
итог задачи139tests+11subtests PASS, git diff --check PASS.


## composer-single-input-20261008

Владелец отменил обязательный ввод переводов своих значений. Причина прежнего
блокирования подтверждена: UI._missing_translation, engine._check_translations,
AIvalidator равенство заполненностиRU/EN. _render брал только заданный языковой
слот. Контроль до правки: RU-onlysubject→ValueError требует английского перевода.
Изменение: один UIinput, source-language slot; renderer fallback на оригинал;
убраны только обязательность пар/переводные guards. Остальные ограничения схемы,
7вариантов/duplicates/hero/locks/exclusions/single-scene сохранены. AIinstruction
требует исходный текст без обязательного перевода; liveповедение не проверено.

Первый baseline UIтест бросилAssertionError о2полях внутри Qtclicked signal,
что завершило pytestSIGABRT. Тестовый harness изменён на прямой вызов редактора:
исключения не пересекают C++ event boundary. Контроль engine повторён отдельно.
Первый большойafter run:151PASS+2subtests/3FAIL ожидания cancelAiButton=None,
оставшегося с периода до добавления постоянной скрытой панелиAI. Проверка
исправлена на отсутствие видимой кнопки вне запроса, без изменения приложения.
Финальные70tests PASS5.44s включают3исправленные assertions и10новых регрессий,
strict AI cases, обеих языков/режимов/mixed,SQLite иsignedComposer. ActualQt
показал белый фон customdialog, из-за которого не читалась подсказка. Для нового
одно-полевого диалога явно заданы Vibix dark background и русские кнопки; actual
single-input.png проверен повторно. Исходные поля/схема не мигрировали, платных
запросов0. Evidence: docs/ui/3.1/composer-single-input-20261008/.


## composer-auto-english-20261008

После отмены ручного двуязычного ввода локальный renderer подставлял русский
оригинал в EN-шаблон. Владелец подтвердил автоматическую подготовку цельного EN.
Диагностика: прежняя инструкция AI запрещала создавать недостающие переводы,
а валидатор сравнивал обе языковые ячейки защищённого поля целиком. Два новых
регрессионных сценария подтвердили отклонение корректно дополненного перевода.

Изменение: получение вариантов при недостающем EN направлено на один AI-запрос
с переводом и генерацией вместе. Существующие языковые значения защищённых
полей сравниваются точно, пустой перевод разрешено заполнить. Итоговый EN и
переводы параметров проверяются на пропуски и кириллицу; остальные ограничения
вариантов и сцен сохранены. Во время ожидания кнопки получения вариантов
блокируются. Ошибка/отмена оставляет прежние данные.

Первичная проверка: 10 новых регрессий PASS; затем 153 tests + 2 subtests PASS.
Дополнительная проверка подписанного пакета сначала обнаружила ошибку fixture:
поле менялось напрямую на экране результатов, где запрос берёт выбранный вариант.
Исправлен тест: сначала переход к параметрам, как в реальном UI; 16 tests PASS.
Проверка реального провайдера не выполнялась: ключ находится на устройстве владельца.
Актуальный итог расширенных проверок и снимки: STATE.md.
Проверка блокировки кнопки сначала выбирала старый виджет, ожидающий Qt
`deleteLater`, через общий findChild. Проверяется текущий footer, как в UI-коде;
это ошибка тестового поиска, а не повторный запрос приложения.


## composer-photography-quality-20261008

Причина слабой детализации: вложенные сценарии заменяли свет/ракурс общими
fallback-фразами, а фотокамера описывалась одинаково. Локальные вариации меняли
только небольшие смещения и заполнение теней. Инструкция AI требовала перевода
и валидной структуры, но не конкретной постановки и фотографической иерархии.

Решение: предметные профили света для 25 направлений, подходящая оптика и фокус
по крупности/типу объекта, конкретный ракурс, естественные фактуры, разные
фотографические акценты. Убрано наследование утреннего времени в вечерние сцены.
Для видео сохранено исходное движение камеры, добавлена стабильность экспозиции
и фокуса. Renderer разбивает текст на читаемые абзацы. AI получает режиссёрские
правила и защиту исходных фактов сцены, без дополнительных запросов или retries.

Проверка первой реализации: 59 PASS, 4 FAIL. Две проверки требовали прежний
один style-вариант и общую fallback-фразу вместо конкретного ракурса; ожидания
обновлены под согласованное поведение, проверки точных сценариев сохранены.
Две проверки многосценного ответа отклонялись раньше, на защите действия/локации,
и теряли ожидаемую причину Reels. Проверка единой сцены перемещена перед защитой
исходных значений, обе ошибки по-прежнему отклоняются. Расширенный прогон:
507 tests + 2 subtests PASS.

Дополнительно: прежние сохранённые стили узнаются по точным aliases без изменения
снимка, старые относительные суффиксы заменяются без накопления. Бьюти-деталь
фокусируется на заданном макияже/коже, макро природы не получает атмосферную
перспективу пейзажа. 76 целевых tests PASS, включая signed module, SQLite,
поля, направления и защиту прежних 69 рецептов по хешам.
Итог полного прогона и семь реальных локальных текстов до/после: STATE.md.
Реальные платные генерации не запускались, качество медиа не заявляется проверенным.

Финальный полный прогон конструктора: 558 tests + 2 subtests PASS (119.66 s).
Последующее уточнение для времени суток: источник случайного «утра» найден в
общих пулах engine после ручной смены style, а не в исходном поле рецепта.
Общий fallback теперь сохраняет заданное время или пустое значение. AI также
не может менять существующий языковой слот времени. Добавлены два сценария
ручного стиля (время пустое/вечер) и отрицательная проверка AI-изменения времени.
Результат последнего целевого прогона отражён в STATE.md.

После уточнения времени 94 целевых tests PASS (49.91 s).
Дополнительная проверка объёма нашла риск повторного усечения: полный локальный
JSON семи подробных вариантов достигал 12 574 токенов в cl100k_base при лимите
12 000 (в o200k_base максимум 9 395). Повторы в описаниях фактур, акцентов,
оптики и стабильности сокращены без удаления конкретных параметров. Инструкция
AI просит краткие незакреплённые поля и полную постановку в итоговом тексте,
защищённые исходные значения сокращать нельзя. Лимит и число запросов сохранены.
Повторное измерение всех 250 рецептов: maxima 8 500/o200k_base и
11 194/cl100k_base. Это измерение синтетического полного ответа двумя эталонными
токенизаторами, а не гарантия всех провайдеров и произвольных длинных вводов.
Evidence: docs/ui/3.1/composer-quality-20261008/response-size.json.
Словари взяты с публичного OpenAI blob через разрешённый read-only download в
/tmp; новых зависимостей приложения нет. Первый локальный запуск токенизатора
не смог получить отсутствующий словарь из sandbox (DNS), повторён с разрешённым
сетевым чтением. Helper запускался с PYTHONPATH=. после исправления пути импорта.

Полный прогон после уплотнения текстов: 561 tests + 2 subtests PASS (112.65 s).
Actual Qt обнаружил одинаковые начала подписей из длинного style-prefix:
названия теперь выделяют изменённую часть вместо повторения базового описания.
79 целевых tests PASS, после фильтрации пустого time из подписи 26 photography
tests PASS. Финальные максимумы с новыми названиями: 8 510/o200k_base,
11 210/cl100k_base. Примеры и Qt-снимки пересозданы из финальных исходников.
## PiAPI submit and balance failures hide rejection reason, 2026-10-13 {#piapi-rejection-diagnostics-20261013}

Owner diagnostics show 73 completed items failed before any `provider_task_submitted`
event across two runs, each with three references; 3 more items were cancelled.
The old request encoded the array of base64 data URLs as one JSON `image` field.
PiAPI's documented multi-image edit contract requires multipart with a repeated
`image[]` file field. This is a confirmed request-format mismatch matching every
failed item. The archive has no HTTP status or provider response body, so we cannot
confirm which HTTP rejection the provider returned. The balance error is separate:
the official `/account/info` URL and `X-API-KEY` header are in use, but the old
dialog hid its sanitized provider error.

Change: encode each local reference as a multipart file part named `image[]`; keep
text fields in the same multipart body. Submission errors record safe HTTP status
and classification; balance UI preserves the typed safe error. Provider response
bodies and credentials remain unlogged. Verification: 96 focused tests +19 subtests
PASS; no live API or paid request performed. The cause of balance failure remains
unknown until the owner checks it using the updated app.

Documentation follow-up: official docs specify the single-file multipart field as
`image` and multiple files as repeated `image[]`; the encoder now follows that split.
The documented async route, `X-API-KEY`, task polling route and account-info
`equivalent_in_usd` parsing match the implementation. Current GPT Image docs list
only `gpt-image-2.5-flare` and `gpt-image-2.5-sunburst`, not the UI's legacy
`piapi/gpt-image-2.5` budget alias. That alias remains unverified and should not be
reported as document-confirmed working. Sources: https://piapi.ai/docs/gpt-image/gpt-image-api
and https://piapi.ai/docs/account-info-api. Focused tests now include one- and
multi-reference multipart field names.

Release preparation check: the version-contract test caught the Azure Windows
pipeline default still set to `3.2.22` after the intended Studio version bump.
Updated that default to `3.2.23`; rerun the release-contract suite before build.

## 2026-10-19 — «Пустые» проекты в списке, заголовок PDF, устаревшие тесты

Симптом: открытие модуля без действий создавало запись проекта (`_replace_shell` сразу
вызывает `_save_draft`). Причина: сохранение не различало «ничего не сделано» и «есть данные».
Решение: снимок состояния после открытия; запись создаётся только если состояние изменилось
или проект уже имеет id или данные заданы заранее (передача результатов в Processing).
Подводный камень, найденный ревью: первая версия теряла проект «результаты → Processing».

Ошибка в новом коде (найдена ревью, не попала в релиз): цикл усечения заголовка PDF отрезал
часть суффикса «— N шт.» и добавлял его обратно — длинное название (типично для Etsy)
зависало экспорт навсегда. Решение: усекается только название. Тест
`test_very_long_title_does_not_hang_and_is_elided`.

Тесты `test_kie_routing` падали до этой работы: заглушка `_fal_source_url` не принимала
`require_https` (после фикса Fal 5131105). Заглушка принимает `**kwargs`.

Проверка: целевые тесты и полный набор pytest (см. STATE.md); живая проверка на компьютере
владельца не выполнялась. Причина зависания CPU после закрытия НЕ установлена: добавлена
только защита (остановка потоков при закрытии).

Остаточные падения полного набора (10 штук) ПРОВЕРЕНЫ НА ЧИСТОМ HEAD до этих правок и
существовали раньше: test_kie_routing (3 Fal-теста) и test_review_worker_recovery (6 Fal-
параметров) — заглушки не знают нового HTTPS-пути Fal (5131105); test_studio_shell_packaging::
test_build_retains_shared_imports_used_by_signed_workflows — ожидает `gpt25_recovery` среди
общих импортов. Не исправлены, нужен отдельный шаг. Полный набор после правок:
3473 PASS, 13 FAIL до исправления моих тестов; затем целевые прогоны PASS.

## 2026-10-19 — мягкая кисть прозрачности почти не отличалась от жёсткой

Причина: «Мягкая» = hardness 50 (плотная середина), падение яркости считалось от радиального
градиента, не доходившего до 0 у края круга, а отпечатки с шагом радиус/3 накапливались
методом paste по маске. Решение: мягкая = 0, спад до 0 ровно у края радиуса, штрих собирается
объединением по максимуму и накладывается на маску один раз (history/undo не менялась).
Проверка: tests/test_soft_brush.py (профиль поперёк штриха, равенство штриха из нескольких
движений одному штриху, undo) и тесты маски/контура PASS. Глазами владельца не проверено.

## 2026-10-19 — зубчатый край штриха кисти прозрачности

Причина: точки мыши округлялись до целых пикселей и соединялись прямыми отрезками, штампы
кисти ставились только в целые координаты. Решение: сглаживание по серединам отрезков +
субпиксельные штампы (1/4 px) + мелкий шаг. Проверка: unit-тесты профиля/кривой и сквозной
тест перетаскивания через QTest; связанные 486 тестов PASS. Глазами владельца не проверено.

## 2026-10-19 — перевод имён экспорта: замечания независимого ревью (исправлены до коммита)

Найдено ревью Opus: сохранение выбора модели срабатывало при построении панели планировщика
и затирало реальный выбор (теперь только по действию пользователя и запуску подбора);
отмена экспорта не прерывала запрос перевода (добавлены проверка отмены и общий срок 90 с);
уведомление «нет ключа» затиралось следующим статусом (теперь входит в статус запуска);
ответ модели не на английском попадал бы в имена (принимаются только ASCII-ответы, иначе
транслит); длинное название проекта обрезало часть «set» (проект ≤70, набор ≤45 символов).
Проверка: tests/test_export_names_translation.py, tests/test_studio_set_export_ui.py.
Живой платный запрос перевода НЕ выполнялся (ключ владельца, по её лимиту).

## 2026-10-19 — мягкая кисть: дёрганая на малых размерах, «полоса» по центру на широких

Причина: на радиусе 0–3 px переход состоит из 1–2 пикселей и выглядит ступенчатым; линейный спад
от центра воспринимался как плотная полоса и резкие края. Решение: MIN_SOFT_RADIUS=4 (диаметры 1/3/6
всегда жёсткие), спад exp(-4.5t²), нормированный до 0 у края. Проверка: tests/test_soft_brush.py
(малые = жёсткие, широкая монотонна, максимальный шаг <20 уровней), 489 связанных тестов PASS.
Глазами владельца не проверено.

## 2026-10-20 — «Vibix Studio висит в задачах и грузит процессор» (диагностика владельца, 3.2.32)

Факты из журнала (VibixImages-diagnostics.zip, 3 сессии): сессия 2026-10-19 закрыта штатно
(application_exit). Сессия 2026-10-20 10:50:35 дошла до license_validation_succeeded (10:50:45) и
дальше НЕ записала ни update_check_started, ни application_exit; следующий запуск 11:00:12 прошёл
нормально (проверка обновлений через 2 с). Вывод: зависание — на СТАРТЕ, между проверкой лицензии
и запуском проверки обновлений, а не при закрытии.
Гипотеза (НЕ доказана, дамп памяти владелец снять не смогла — файл ~500 МБ): refresh_license_status
в основном потоке для каждого установленного модуля вызывает ModuleStore.verified_active_path →
полная переподпись/хеширование всех файлов пакета; на холодном диске/антивирусе это минуты CPU.
Предложенное исправление (ждёт «делай»): проверять модули один раз в фоновом потоке и кэшировать
результат по размерам/mtime; добавить принудительное завершение процесса через 5 с после закрытия
окна; писать в журнал длительность этапов запуска, чтобы подтвердить причину.

Исправление (2026-10-20, ветка codex/projects-export-hardening-20261019, не собрано/не опубликовано):
1) refresh_license_status больше не хеширует модули в главном потоке: ModuleStore.cached_verification
   (кэш вердикта по отпечатку имён/размеров/mtime) + ModuleStore.verify_for_display в фоновом
   QThread (_ModuleVerifyThread); загрузчик кода по-прежнему делает ПОЛНУЮ проверку
   (studio_module_runtime → verified_active_path) — безопасность не ослаблена;
2) страховка: через 5 с после закрытия окна процесс завершается os._exit(0), но только в
   установленном (frozen) приложении — иначе она убивала pytest (поймано при проверке);
3) журнал: события startup_status_refreshed (refresh_ms), module_verification_finished
   (длительность по модулям), application_ui_ready.details.build_ms, exit_watchdog_armed —
   по ним при повторе будет видно, какой этап был долгим.
Тесты: tests/test_startup_hang_fixes.py; полный набор 3501 PASS, 10 прежних падений (Fal/packaging).
Причина зависания всё ещё не доказана; если повторится — прислать журнал диагностики.

## 2026-10-20 — независимое ревью (Opus 5.5) правок A–E и исправления зависания

Найдено и исправлено до сборки: (1) закрытие окна во время фоновой проверки модулей роняло процесс
(«QThread: Destroyed while thread is still running») — поток теперь без родителя, держится в
наборе до завершения, closeEvent ждёт до 1.5 с; (2) сбой при проверке (заблокированный файл) мог
запускать проверку бесконечно — теперь любая ошибка = «не проверено» без исключения, каждый модуль
проверяется один раз за сессию; косметика: событие exit_watchdog_armed пишется до закрытия журнала.
Не исправлено осознанно (низкий риск): страховка выхода через 5 с может оборвать воркер, если он
не остановился за 3 с; без неё процесс остался бы висеть. Безопасность кэша проверки подтверждена:
загрузчик модулей по-прежнему делает полную проверку. Тесты: tests/test_startup_hang_fixes.py.


## Приёмка 3.2.34 (2026-10-20): кнопки, мягкая кисть

- Шапка: «API» была не цвета иконок, на иконке «Продолжить» оставалась синяя рамка фокуса. Решение: «API» бирюзовым (accent), у кнопок шапки NoFocus; рамкой выделяется только «Обновления модулей» при доступных обновлениях.
- Кнопки V3: у нажатого/отключённого состояния нечитаемый текст (пунктирная рамка, низкий контраст). Решение: явные :pressed, отключённая кнопка — светлый текст, обычная рамка. В «Модулях Studio» «Обновить все модули» появляется вместо «Проверить обновления модулей» только когда проверка нашла обновления установленных модулей.
- Мягкая кисть: гауссиан начинал спад от центра, мазок выглядел в 3–4 раза тоньше жёсткого. Решение: сплошное ядро ≥55% радиуса (+ жёсткость), спад smoothstep только во внешней полосе до нуля на краю — ширина как у жёсткой. Тесты tests/test_soft_brush.py обновлены.
- Шаг «Проверка» Auto Clipart: «Проверить прозрачность» теперь главная (выделена), «Открыть папку» обычная; у кнопок подсказки. Назначение/необходимость «Продолжить незавершённые», «Начать заново», «Обработать выбранное» — вопрос владельцу.
- НЕ ошибка кода: значки на шаге «Идеи» и шкала добавления файлов в «Обработке» не видны в 3.2.34, потому что это код подписанных модулей auto-clipart/processing — они дойдут только с новыми подписанными пакетами (ключ у владельца).
- Проверка: pytest (run_queue, auto_clipart_workflow, module_update_ui, outline_actions, v3_components, ideas_step_layout, soft_brush, background_mask) — зелёные; визуально на Windows не проверено.
- Шаг «Проверка» Auto Clipart (решение владельца 2026-10-20): «Обработать выбранное» скрыта (код и связка сохранены), «Начать заново» не показывается в режиме Clipart, основная кнопка одна по ситуации: «Доделать оставшиеся (N)» → иначе «Проверить прозрачность»; «Открыть папку» — обычная. Отложено: «Сгенерировать выбранные заново» (платная операция; нужен явный расчёт стоимости и подтверждение, существующая защита «нет PNG — не перегенерировать платно» не ломать). Правило владельца: если доработан подписанный модуль — агент сам предлагает собрать пакет модуля.
- Закрытие/«Домой» (приёмка 3.2.34, 2026-10-20): крестик и «Домой» молча не срабатывали в модуле Clipart после остановленного прогона — переход блокируется, пока контроллер «занят» (рабочий поток/ожидающий подбор идей/экспорт), а причина показывалась лишь мелкой строкой внизу. Корневая причина «занятости» в этом случае НЕ установлена (нет журнала владельца). Решение: крестик и «Домой» теперь спрашивают «Остановить и закрыть/перейти?», останавливают рабочие потоки и не держат пользователя; в журнал пишется причина (close_blocked_by_busy / leave_blocked_by_busy: active_run | controller_busy). Если повторится — смотреть журнал. Проверка: тест _busy_reason; поведение на Windows не проверено.
- «Обновить расчёт» (запрос владельца 2026-10-20): кнопка есть на шаге запуска (Clipart/Auto Clipart/Pinterest/Генерация — всегда, раньше только «Обновить оценку Fal.ai» при выборе Fal) и на «Проверка и запуск» Обработки. Пересчёт по текущим настройкам + актуальная цена Fal.ai (host.image_run_estimate_fal_cost); при смене настроек прежняя котировка Fal сбрасывается. ЖИВЫХ цен у KIE/AtlasCloud/PiAPI/PhotoRoom нет (публичного API цен не подтверждено) — берутся из каталога в приложении (честно указано «ориентировочно»). Страница запуска — ядро; страница Обработки — модуль processing (нужен новый пакет).

## Вырезание: зелёный фон для объектов с листьями, туман прозрачности (2026-10-21)

- Симптом: у вырезанного утёнка с ромашками размытые края листьев, голубой обрывок между листьями, слабая «дымка» (прозрачность 1–40 из 255) вокруг контура и между деталями, максимум прозрачности 254.
- Причина 1: режим фона «Авто» (chroma_key_selection.py) выбирал цвет по словам описания; «ромашки/цветы» не считались признаком листьев, а при ничьей порядок был синий → зелёный → красный. Описание «розовая шапка, ромашки, голубой бант» давало зелёный фон, листья сливались с ним.
- Решение: слова про цветы/букеты/венки и про деревья, ёлки, кусты, хвою, плющ, папоротник, пальмы добавлены в признаки зелени; порядок выбора синий → красный → зелёный (зелёный последний). Тест: test_flowers_imply_leaves_so_green_is_not_chosen.
- Причина 2: порог прозрачности хромакея 2,5 %, зачистки мелких островков с кольцом не было. Решение: alpha_cleanup.py (туман ниже 16 % дальше 3 px от объекта, острова меньше ~214 px с кольцом, сужение гладких краёв до 1–2 px, пух не трогается, прозрачность ≥ 98,5 % → 255), подключено после локального хромакея; пропускается при локальном Real-ESRGAN после вырезания (контракт «вход нейросети = выход движка»).
- Проверка: tests/test_alpha_cleanup.py (8), test_chroma_key_selection.py, замер на файле утёнка (туман 45 тыс. → 0 px, лапки 6 → 2,4 px, RGB не изменён). НЕ проверено на исходниках генерации (их нет): края листьев/банта на реальных вырезаниях, живой вид в окне.

## «Обновить все модули» требовало второго нажатия (2026-10-21, версия 3.2.38)

- Симптом: после одной кнопки «Обновить все модули» обновлялся только верхний модуль, остальные оставались на прежней версии с кнопкой «Обновить».
- Причина: первое обновление было общим (WorkflowUpdate); ветка общего обновления останавливала очередь и сбрасывала предложения, а автоматическая перепроверка (3.2.35) только возвращала кнопки, не продолжая очередь.
- Решение: studio_module_update_ui.py — после общего обновления очередь помнит число уже обновлённых, перепроверка запускается сама и «Обновить все» продолжается сама (не больше числа модулей раз, при ошибке проверки не продолжается). Итог «Готово: обновлены все N модулей».
- Проверка: tests/test_studio_module_update_ui.py::test_update_all_continues_by_itself_after_a_shared_update (падает без правки, проходит с ней), 18 тестов файла, полный прогон. Живое окно не проверялось.

## Туман и мягкие края у результата с родной прозрачностью модели (2026-10-21)

- Уточнение владельца: генерация шла с прозрачным фоном (родная alpha модели), а не на цветном фоне. Поэтому выбор цвета фона и зачистка после хромакея (3.2.37) этот результат не затрагивали.
- Причина: ветка «использована сохранённая alpha-маска» (main.py, native_alpha.preserve_native_alpha) намеренно не меняла прозрачность модели, вместе с ней проходили слабая «дымка» вокруг контура и мягкие края.
- Решение: после preserve_native_alpha применяется alpha_cleanup.clean_alpha(clear_hidden_rgb=True): слабые одиночные пиксели и мелкий мусор убираются, гладкие края сужаются, плотное ядро сохраняется точно; цвет под нулевой прозрачностью обнуляется. Старый тест «alpha сохраняется побайтно» (test_native_alpha_route_preserves_detail_without_chroma_call) переписан под новый контракт. Прозрачные материалы (стекло, вуаль) в режиме непрозрачного клипарта не поддерживаются, мелкие полупрозрачные детали могут стать плотнее.
- Проверка: tests/test_alpha_cleanup.py, test_local_processing_acceptance.py, test_chroma_nn_working_alpha.py; полный прогон перед релизом. Не проверено на реальных генерациях модели.

## 2026-10-21 — после «Да» в подтверждении запуска ничего не происходит (3.2.38, Windows)

- Симптом: в открытом сохранённом проекте с новыми 50 промптами диалог платного запуска
  закрывается, генерация не стартует, шаги не переключаются, крестик не закрывает окно;
  в журнале десятки `save_failed`.
- Корневая причина (установлена по файлу проекта пользователя): `automatic.previous_runs`
  хранил полный архив 50 промптов на каждую смену набора (~280 КБ каждый). Накопилось
  10 архивов, файл проекта стал 1,92 МБ при лимите 2 МБ (`MAX_PROJECT_BYTES`). Следующий
  архив превышал лимит, и каждое сохранение падало («Project exceeds size limit»).
  Запуск начинается с сохранения проекта, поэтому он отклонялся; причина писалась только
  на скрытую страницу. Закрытие окна при неудачном сохранении молча отменялось.
  Журнал терял причину: ключи `error`/`cause` не входили в разрешённые поля.
- Исправление: история запусков обрезается с самых старых архивов (бюджет 1 МиБ, максимум
  100), см. `_archive_run`; отказ запуска после «Да» показывается окном; закрытие при
  неудачном сохранении спрашивает «Закрыть без сохранения?»; `save_failed` пишет
  `error_code` (цепочка классов) и `error_message`.
- Проверка: `tests/test_auto_clipart_workflow.py` — новые тесты на обрезку истории,
  видимый отказ запуска, закрытие при неудачном сохранении и содержимое журнала.
- Примечание: у пользователя проект уже содержит 1,86 МБ истории; она обрежется при
  следующем архиве. Если сохранение ещё не проходит, нужен файл проекта.

## Белая подложка и мелкие цветы у венков и рамок Auto Clipart (2026-10-22)

- Симптом: на сырых генерациях на синем фоне вокруг мелких цветов между веточками лежат белые рваные пятна («подложка»), в щелях остаётся синий, мелкие цветы мутные. Набор Little Goose Garden Party, PiAPI GPT Image 2.5 Flare, только 1K (1024×1024).
- Причина (вероятная, не доказана полностью): промпты просили «полевые травы и цветы» и «пышные композиции», палитра содержала почти белые #FCF0E9 #EFE7D9, а запрета белой подложки ни в промпте, ни в блоке фона не было. Белая подложка непрозрачна, поэтому chroma-ключ её не убирает; QC (studio_alpha_qc) смотрит только на итоговую alpha и такой дефект не ловит.
- Неправильная попытка: тестовый промпт без россыпи мелких цветов подложку не воспроизвёл (контроль A тоже был чистым), вывод по нему был бы пустым. Выбор синего цвета автоподбором (chroma_key_selection) смотрит только на слова промпта и сам по себе причиной не признан.
- Решение (владелец: качество важнее пышности): в studio_commercial_prompt_guidance.py добавлены запрет белой/кремовой подложки для всех ролей, лимит 5–8 крупных цветков для венков и рамок, правило «почти белые тона палитры только для лепестков»; та же фраза в chroma_key.chroma_key_prompt_block.
- Проверка: tests/test_clipart_quality_prompt_rules.py (10) и 182 существующих теста chroma/clipart-flow проходят. Это проверка текста промптов, а не качества генерации: на реальных картинках подтверждён только вариант D (запрет + палитра без белого) без контроля A; A, B, C не сгенерировались из-за перегрузки провайдера. Нужна повторная серия A/B/C. Уже сохранённые вручную промпты не меняются.
