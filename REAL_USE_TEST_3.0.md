# REAL_USE_TEST_3.0

Эксплуатационная проверка `v3.0.0-rc1`. Код, WorkerThread, RunPod, SynthID и installer в этом тесте не изменяются.

Для каждого шага заполнить: ожидаемый результат, фактический результат, `PASS/FAIL/BLOCKED`, изменились ли исходники, время, API/локальный модуль и стоимость.

## Сценарий A — Clipart

| Шаг | Действие | Ожидаемый результат | Факт | Статус | Исходники | Время | API/модуль | Стоимость |
|---|---|---|---|---|---|---|---|---|
| A1 | Новый проект и рабочая папка | Режим открывается без падения |  |  |  |  | local UI | 0 |
| A2 | Добавить 20+ промптов | Все строки отображаются |  |  |  |  | local UI | 0 |
| A3 | Добавить референсы к нескольким строкам | Референсы привязаны к своим строкам |  |  |  |  | file picker | 0 |
| A4 | Перетащить строки | Текст и референсы перемещаются вместе |  |  |  |  | local UI | 0 |
| A5 | Выбрать модель и параметры | Совместимая модель и стоимость видны |  |  |  |  | KIE | по модели |
| A6 | Выполнить генерацию | Результаты и прогресс доступны |  |  |  |  | KIE API | платно |
| A7 | Применить обработку | Output создан, исходники неизменны |  |  |  |  | local/KIE/PhotoRoom | по provider |
| A8 | Сохранить результаты и проект | Файлы и draft сохранены |  |  |  |  | filesystem/JSON | 0 |
| A9 | Закрыть и открыть снова | Промпты, референсы, модель и операции восстановлены |  |  |  |  | local JSON | 0 |

## Сценарий B — Pinterest

| Шаг | Действие | Ожидаемый результат | Факт | Статус | Исходники | Время | API/модуль | Стоимость |
|---|---|---|---|---|---|---|---|---|
| B1 | Новый проект | Pinterest открывается без падения |  |  |  |  | local UI | 0 |
| B2 | Добавить несколько промптов и референсов | Данные редактируются и не смешиваются |  |  |  |  | local UI | 0 |
| B3 | Текстовая модель | Выбор и вертикальная пропорция применяются |  |  |  |  | KIE | по модели |
| B4 | Reference-модель | Совместимая пара разрешается, несовместимая блокируется |  |  |  |  | KIE | по модели |
| B5 | Отдельный шаг обработки | Шаг доступен и не смешан с генерацией |  |  |  |  | local/provider | по provider |
| B6 | Генерация | Изображения и прогресс доступны |  |  |  |  | KIE API | платно |
| B7 | Сохранить, закрыть, открыть | Результаты, проект и настройки восстановлены |  |  |  |  | filesystem/JSON | 0 |

## Сценарий C — Processing

| Шаг | Действие | Ожидаемый результат | Факт | Статус | Исходники | Время | API/модуль | Стоимость |
|---|---|---|---|---|---|---|---|---|
| C1 | Добавить 20+ изображений | Все файлы отображаются строками |  |  |  |  | file picker | 0 |
| C2 | Включить trim | Trim применяется по настройке |  |  |  |  | local pipeline | 0 |
| C3 | Включить 300 DPI | Output имеет 300 DPI |  |  |  |  | local export | 0 |
| C4 | Очистить метаданные | EXIF/XMP/IPTC удалены, ICC/DPI сохранены |  |  |  |  | local cleanup | 0 |
| C5 | Удалить фон | Alpha сохраняется у alpha-safe provider |  |  |  |  | rembg/BEN2/PhotoRoom/KIE | по provider |
| C6 | Выполнить upscale | Размер/качество соответствуют модели |  |  |  |  | Real-ESRGAN/provider | по provider |
| C7 | Отменить обработку | Worker останавливается безопасно |  |  |  |  | local/provider | возможно платно |
| C8 | Ошибка одного файла | Ошибка изолирована, успешные файлы доступны |  |  |  |  | local pipeline | 0 |
| C9 | Collision/overwrite | Поведение перезаписи соответствует настройке |  |  |  |  | filesystem | 0 |
| C10 | Сравнить исходники | Исходные файлы не изменились |  |  |  |  | hash/filesystem | 0 |

## Негативные сценарии

- пустые промпты/файлы/API key: понятная ошибка, worker не запускается;
- повреждённый CSV или файл: ошибка с причиной и номером строки/файла;
- отсутствующий reference: предупреждение без потери промпта;
- несовместимая модель: запуск блокируется;
- ошибка сети/provider: ключи и пути не попадают в сообщение;
- отмена: исходники и уже готовые результаты сохраняются.

## Проблемы

| ID | Severity | Точные шаги | Пользовательское влияние | Техническая причина | Ветка | Статус |
|---|---|---|---|---|---|---|
|  | Critical/High/Medium/Low |  |  |  | `release/3.x` bugfix или `develop/3.0` улучшение | Open/Fixed/Blocked |

## Подготовка

- 20+ PNG/JPEG/WebP;
- 20+ промптов и CSV с нестандартными заголовками;
- 3–5 референсов;
- пустая output-папка;
- одинаковые имена для collision-теста;
- один повреждённый файл.

Платные действия: генерация KIE, платное удаление фона/upscale и cloud GPU. Локальные операции, CSV, draft, metadata cleanup и hash-проверка бесплатны. Исходники не должны изменяться: использовать отдельную output-папку и не включать overwrite до отдельного теста.

## Current execution record — 2026-07-31

| Area | Status | Evidence / limitation |
|---|---|---|
| Processing wizard opens in the GUI | VERIFIED | Computer Use reached `Режим: Обработка изображений`; no crash during entry |
| Processing GUI full run with test copies | VERIFIED | Manual native-file-picker smoke completed: files added, Processing stage shown, separate output used, results saved there, README.jpg handled or explicitly failed, remaining files continued, sources unchanged, no paid API started |
| Processing output directory, stage label, missing-file reason | VERIFIED | Targeted regression tests cover `output_dir`, `processing`, and explicit unavailable-file status |
| `README.jpg` in a multi-file local batch | VERIFIED | Regression confirms both `README.jpg` and a neighboring JPEG produce outputs |
| Local processing preserves source and writes a new output | VERIFIED | Real local pipeline regression with SHA-256 source check |
| Paid external API calls | NOT RUN | No KIE, PhotoRoom, RunPod, or other paid operation was started |
| Source safety | VERIFIED | Tests use temporary copies; repository worktree remained clean after GUI attempt |
| Mode switching preserves project data | VERIFIED | Isolated wizard/mode regression: `test_mode_switcher_reuses_project_and_switches_immediately`, `test_mode_switch_applies_immediately_and_preserves_data` |
| Pinterest navigation preserves prompts and format | VERIFIED | Isolated regression: `test_navigation_preserves_project_prompts_and_format` |
| Draft snapshot and restore across project/shell recreation | VERIFIED | Isolated regressions cover snapshot/continue, disk draft restore, shell recreation, and prompt data after navigation (`4 passed`) |
| Paid-provider preflight and explicit run boundary | VERIFIED | Isolated Clipart/Pinterest regressions block missing keys, invalid references, unknown models and partial prices before worker (`5 passed`); no provider call made |
| Processing cancel, isolated failure and collision safety | VERIFIED | Queue regressions cover cancellation boundaries, preserving completed items, retrying only failed items, rejecting untrusted/missing outputs, and preserving sources (`8 passed`, `2 subtests`) |
| Processing trim, metadata preservation and 300 DPI export | VERIFIED | Focused local regressions cover trim ordering, alpha preservation, metadata/DPI carry-over, and 300 DPI final export (`5 passed`) |
| Local alpha-safe background/upscale paths | VERIFIED | Local Real-ESRGAN size/alpha checks, deterministic edge controls, missing-tool diagnostics, and paid-provider fail-closed checks (`5 passed`, `2 subtests`) |
| Clipart/Pinterest local routes, prompts and request boundaries | VERIFIED | Focused route, prompt/CSV, pipeline summary, secret-redaction and no-network module checks (`10 passed`); no provider-backed generation started |
| Credentials, secret redaction and provider-contract mocks | VERIFIED | Isolated security regression covers env credential round-trip, KIE routing, no-network local generation, redirect/header protection, top-level error redaction, and PhotoRoom diagnostics (`8 passed`, `5 subtests`) |
| Qt lifecycle smoke and grouped-suite stability | MANUAL PENDING | Extended V3 route suite passes (`32 passed`, `8 subtests`, 51.76 s); a fresh full `pytest -q --disable-warnings --maxfail=1` still did not finish within 300 s, so legacy Qt lifecycle remains unconfirmed |
| Processing Results UX block | MANUAL PENDING | Error/status tokens, collision policy, fixed action bar, Done and Process-more contracts have targeted regression coverage; offscreen 980×700 render confirms fixed geometry but native rendered/manual verification remains pending |
| Processing UX targeted regression after implementation | VERIFIED | Shared Processing/wizard/Clipart/Pinterest suite: `95 passed`, `13 subtests`; user-facing summary now includes output folder and technical details are deferred to the technical log; `py_compile` and `git diff --check` pass |
| Full Clipart/Pinterest real provider run | MANUAL PENDING | No paid generation was started; provider-backed output still requires a separate approved manual smoke |
