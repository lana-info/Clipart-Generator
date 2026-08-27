# PRD

## Goal

Clipart Generator должен помогать автору быстро генерировать и доводить до продажи PNG-клипарты: создавать изображения по промптам или референсам, обрабатывать локальные файлы, улучшать качество, удалять фон, чистить край объекта, обрезать пустые поля и сохранять готовые файлы в рабочую папку.

Главная цель продукта - дать стабильный desktop-инструмент для подготовки клипартов к Etsy/маркетплейсам с контролем качества, стоимости и локальной обработки там, где это дешевле или надёжнее облака.

## Users

- Автор цифровых товаров, который делает наборы клипартов и хочет получать готовые PNG без ручной обработки каждого файла в Photoshop.
- Оператор приложения, который запускает генерацию или пакетную обработку локальных изображений.
- Разработчик/поддержка, который должен безопасно улучшать pipeline без поломки работающего интерфейса и уже проверенных сценариев.

## MVP

- Генерация изображений через поддерживаемые KIE-модели в режимах text-to-image и image-to-image.
- Пакетная обработка локальных файлов без обязательной генерации.
- Опциональное локальное удаление небольшой видимой метки до первого апскейла: Gemini автоматически или другая метка в подтвержденной пользователем области.
- Независимый апскейл до и/или после удаления фона через KIE или Local Real-ESRGAN.
- Удаление фона через KIE, PhotoRoom Standard или Local rembg. BEN2 остаётся
  исследовательским скриптом и не показывается в релизном приложении, пока его
  тяжёлые runtime-зависимости не будут отдельно одобрены и воспроизводимо упакованы.
- Опциональный Unsharp Mask после апскейла.
- Опциональное удаление края/контура объекта на `1/2/3 px`.
- Финальный trim пустых краёв.
- Сохранение PNG, включая прозрачность и 300 DPI при включённой настройке.
- Сохранение пользовательских настроек между запусками.
- Понятные логи прогресса без вывода секретов и лишних команд.

## Core Workflows

1. Автор выбирает рабочую папку, вводит промпты, выбирает модель генерации, пропорции и качество, запускает генерацию и получает результаты в `output/`.
2. Автор выбирает существующие изображения, включает нужные шаги обработки, запускает process-only режим и получает обработанные PNG в `output/`.
3. Автор выбирает локальный pipeline: optional visible-mark cleanup -> optional Real-ESRGAN до фона -> Unsharp Mask -> Local rembg -> optional Real-ESRGAN после фона -> edge shrink -> trim.
4. Автор выбирает смешанный pipeline, когда часть шагов выполняется локально, а часть через KIE.
5. Автор проверяет промежуточные файлы в `raw/`, если результат выглядит неправильно.
6. Только после явного решения автора о готовности приложения поддержка вручную запускает release workflow и не смешивает основной repo с repo обновлений. Обычный push не запускает сборку или релиз.

## Processing Order

Фиксированный порядок обработки:

1. Optional local visible-mark cleanup.
2. Optional upscale before background removal.
3. Optional Unsharp Mask.
4. Remove background.
5. Optional upscale after background removal.
6. Edge contour removal.
7. Final trim.
8. Optional final metadata/C2PA inspection and cleanup.
9. Atomic save PNG.

Этот порядок должен оставаться предсказуемым: UI показывает шаги в том же порядке, в котором они выполняются.

## Post-MVP Roadmap

### Export Cleanup

Source of truth for supported claims: [`CLEANUP_CAPABILITY_MATRIX.md`](./CLEANUP_CAPABILITY_MATRIX.md).
Structured hidden-marker result contract: [`PIXEL_WATERMARK_STATUS_CONTRACT.md`](./PIXEL_WATERMARK_STATUS_CONTRACT.md).

- Добавить отдельный блок очистки итогового файла с одной понятной галочкой полной очистки.
- Разрешить удаление метаданных: EXIF, XMP, IPTC, комментариев, встроенных миниатюр и служебных данных генератора.
- Сохранять нужные для экспорта данные отдельно: цветовой профиль и 300 DPI не должны удаляться без явного выбора пользователя.
- Исследовать обнаружение и удаление видимых служебных меток генераторов, включая метки Nano Banana, только для собственных или лицензированных изображений пользователя.
- Исследовать скрытые метки и данные происхождения изображения. Отдельно различать удаляемые метаданные/манифесты и встроенные в пиксели сигналы, удаление которых может быть технически ненадёжным.
- Перед сохранением показывать в логе, какие категории данных найдены и какие действия реально выполнены.
- Не обещать гарантированное удаление всех скрытых нейросетевых маркеров без подтверждённого теста для конкретного формата и источника.
- В первой версии поддерживать metadata inspection/cleanup только для однокадровых PNG/JPEG с итоговым экспортом в новый PNG.
- SynthID и неизвестные пиксельные маркеры не смешивать с metadata cleanup. Для них допускается отдельный экспериментальный режим полной перегенерации любых принадлежащих пользователю изображений с обязательным предупреждением об изменении всех пикселей и без обещания гарантированного удаления.
- Результат перегенерации и результат проверки пиксельной метки хранить отдельно: `succeeded` не означает `removed`, а `not_detected` не доказывает человеческое происхождение. Для непроверенного SynthID показывать официальный Gemini handoff, для неизвестной метки - ручную или внешнюю проверку.
- Видимые небольшие метки обрабатывать отдельным локальным opt-in шагом до первого апскейла. Автоматический режим разрешен только для подтвержденной метки Gemini; для Doubao, Jimeng, Samsung и неизвестных меток требуется подтвержденная пользователем ограниченная область. Нераспознанное изображение оставлять без изменений.
- Для видимой метки Gemini использовать локальное обратное восстановление по известной alpha-маске. Для подтвержденной пользователем небольшой служебной метки использовать встроенный локальный MI-GAN с ограниченной маской и мягким внутренним переходом. KIE не предлагать в этом режиме: Task 33 показал полную перерисовку изображения вне маски. Функция выключена по умолчанию и предназначена только для небольших служебных меток на собственных или лицензированных PNG/JPEG.
- Tasks 39-41 отклонили managed API как универсальный путь. KIE GPT Image 2 изменил размер и потерял alpha, KIE FLUX 2 Pro загрязнил результат контрольной сеткой, OpenRouter Recraft заменил сюжет/лицо/текст, а Seedream изменил детали лица и фото, потерял alpha и добавил C2PA. Riverflow сохранил изображение лучше остальных, но потерял alpha, не дал detector evidence и сообщил `$0.264885` против endpoint snapshot `$0.130`. Managed provider в приложение не добавляется.
- Task 42 завершён как local production hardware no-go без загрузки model weights: на текущем Windows-компьютере нет поддерживаемого CUDA/XPU/MPS accelerator, upstream не поддерживает AMD DirectML, а CPU-путь требует FP32 и как минимум `12.92 GiB` весов SDXL, `15.25 GiB` с ControlNet или `53.74 GiB` Qwen. Медленный plain-SDXL CPU route технически не объявляется невозможным, но CPU-only исключён как production candidate. Tasks 43-49 пропущены; whole-image regeneration и её UI в приложение не добавляются.
- Если GPU serverless будет пересматриваться в будущем отдельным решением, использовать только scale-to-zero endpoint. Обычный CPU VPS может быть защищённым gateway/queue и не должен выполнять diffusion inference.
- Проверять видимое качество, стоимость и доступный внешний detector после обработки. Облачный результат повторно инспектировать, потому что provider может добавить собственные metadata или pixel-level markers.

## Constraints

- Основной код приложения находится в `main.py`, GUI построен на PyQt6.
- Пользовательские данные хранятся вне репозитория в `%LOCALAPPDATA%\Clipart Generator`.
- Нельзя печатать API keys, license keys, пароли или `.env` в логи, документацию и ответы.
- Удалённые API/license URL должны использовать HTTPS; redirect не должен переносить секретные заголовки или понижать соединение до HTTP, ответы и загрузки должны иметь размерные лимиты, а неоднозначный non-idempotent POST нельзя повторять автоматически.
- KIE API key требуется только для выбранных шагов, которые реально используют KIE.
- PhotoRoom API key требуется только при выбранном `PhotoRoom Standard` и хранится в отдельном скрытом поле настроек.
- Local-only pipeline должен работать без KIE API key.
- Local Real-ESRGAN binaries/models не должны попадать в git.
- Для Local Real-ESRGAN доступны только проверенные локальные scale `2x` и `4x`.
- При апскейле прозрачных PNG alpha-канал должен сохраняться.
- Правки должны быть узкими: не менять работающий UI или pipeline без прямой связи с задачей.
- Новые зависимости добавлять только при явной пользе и после проверки влияния на сборку.
- Очистка видимых или скрытых меток допускается только для изображений, которыми пользователь вправе распоряжаться.
- Очистка метаданных должна быть выборочной и не должна случайно удалять нужные для печати DPI или цветовой профиль.
- Любая GPU/API интеграция должна иметь timeout, cancellation, размерные лимиты, временное хранение и удаление файлов после завершения.
- Секрет GPU endpoint не должен встраиваться в распространяемое desktop-приложение; при managed distribution он хранится на обычном VPS gateway.

## Out Of Scope

- Полная замена PyQt6-интерфейса.
- Автоматическая публикация товаров на Etsy.
- Постоянный always-on GPU server и diffusion inference на обычном CPU VPS.
- Долговременное хранение пользовательских изображений на KIE, OpenRouter, GPU worker или VPS gateway.
- Новая платёжная система или изменение лицензирования без отдельного ТЗ.
- Массовый рефакторинг `main.py` без отдельной задачи и проверки.
- Автоматический обход CAPTCHA, 2FA или чужих ограничений сервисов.

## Acceptance Criteria

- [x] Приложение запускается без ошибок в текущем окружении.
- [x] Старые config-файлы открываются, а отсутствующие новые ключи получают безопасные defaults.
- [x] Generate-only сценарий сохраняет изображения в `output/`.
- [x] Process-only сценарий работает на локальных PNG/JPG без генерации.
- [x] Local-only processing не требует KIE API key.
- [x] Mixed local/KIE processing требует KIE API key только для KIE-шагов.
- [x] Local Real-ESRGAN `2x` и `4x` создают изображение ожидаемого размера.
- [x] Local Real-ESRGAN сохраняет alpha у прозрачных PNG.
- [x] Апскейл можно независимо включать до фона, после фона или в обеих позициях; общий множитель показывается до запуска.
- [x] Удаление фона сохраняет PNG с alpha.
- [x] PhotoRoom Standard работает в process-only без KIE API key и сохраняет PNG/RGBA.
- [x] Edge shrink меняет только alpha-край и не портит RGB.
- [x] Исследовательский BEN2-скрипт в отдельном окружении не создаёт
  полупрозрачный край при `softness 0`; в релизном приложении BEN2 не выбирается.
- [x] Trim удаляет пустые края в конце pipeline.
- [x] UI сохраняет и восстанавливает настройки обработки.
- [x] В `raw/` сохраняются промежуточные файлы для диагностики.
- [x] Metadata cleanup очищает EXIF/XMP/IPTC/comments/thumbnail/generator/C2PA одной галочкой и сохраняет ICC/DPI.
- [x] Cleanup-only process запускается без KIE API key и публикует новый PNG атомарно.
- [x] Metadata-only стадия не меняет размеры, декодированные пиксели или alpha; ICC/DPI сохраняются согласно выбранным настройкам.
- [x] C2PA cleanup ограничен локальным manifest/ссылкой в новом PNG и не заявляет удаление remote/sidecar/pixel signals.
- [x] Видимая метка Gemini может быть удалена локально до первого апскейла; остальные небольшие метки требуют подтвержденную область, а KIE key не нужен.
- [x] Выключенная очистка видимой метки сохраняет прежний UI, pipeline и результат без изменений.
- [ ] Перед релизом пройдены проверки из `TEST_CHECKLIST.md`.

## Related Documents

- [`PROJECT_KNOWLEDGE_BASE.md`](./PROJECT_KNOWLEDGE_BASE.md)
- [`PROCESSING_PIPELINE_TZ.md`](./PROCESSING_PIPELINE_TZ.md)
- [`LOCAL_PROCESSING_PROJECT_PAGE.md`](./LOCAL_PROCESSING_PROJECT_PAGE.md)
- [`CLEANUP_CAPABILITY_MATRIX.md`](./CLEANUP_CAPABILITY_MATRIX.md)
- [`TASKS.md`](./TASKS.md)
- [`CHANGELOG.md`](./CHANGELOG.md)
- [`TEST_CHECKLIST.md`](./TEST_CHECKLIST.md)
- [`TASK50_CLEANUP_ACCEPTANCE.md`](./TASK50_CLEANUP_ACCEPTANCE.md)

## Next Product Phase: Prompt Quality, Localization, and Fal.ai

This section defines the next implementation phase after the current 3.0
stabilization. It does not expand the current release promise and does not
authorize Patterns, mockups, invitations, Canva export, or modular licensing.

### Objective

Improve the existing clipart generation workflow so a Russian-speaking author
can describe an idea naturally, review a clear structured prompt, generate a
coherent series, and use Fal.ai operations where the selected model and
provider capabilities allow it.

### Workflow and page composition

The application must not force every workflow to use the same pages, prompt
builder, or processing controls. Before commercial module licensing exists, it
will use workflow definitions that compose shared and workflow-specific pages.

A workflow definition may specify ordered pages, prompt schema, prompt-builder
behavior, allowed operations, visible provider controls, validation, exports,
and explanatory copy. Shared infrastructure remains common, while a future
TrendWatcher-like prompt builder can be added as a separate workflow-specific
page without forking the whole application.

It may also define an ordered step graph after generation or processing. Steps
can include core processing, local export, document/package creation, review
gates, and external delivery. For example, a workflow can finish with a PNG,
continue to PDF creation, prepare a Canva-compatible package, or upload an
approved artifact to Google Drive. Each step must declare its input artifact
types, output artifact types, validation, retry/cancel behavior, and whether it
has an external side effect.

Local exports and external delivery are different contracts. PDF/Canva
creation may run locally after the user confirms the result. Google Drive or
another connector requires explicit user confirmation, an identified account
and destination, a visible upload status, safe retry behavior, and no upload on
preview or ordinary save. A failed delivery must not invalidate or overwrite a
successfully created local artifact.

Visibility is workflow- and capability-driven. A function with no user value is
omitted completely rather than shown disabled. For example, transparency and
background cleanup can be offered in Clipart, while being absent from Pinterest
if that workflow does not need them. Hidden operations must also be excluded
from run-plan validation, saved defaults, accessibility traversal, and
diagnostics summaries, including when stale settings are loaded.

### Decisions and gates before implementation

- The first clipart generator accepts structured fields. Reliable parsing of a
  single free-form Russian sentence and creative rewriting are separate future
  actions; they are not implied by the base template.
- The clipart structured data is the source of truth. The rendered UI/provider
  prompt is derived from it. Editing a rendered string does not promise a
  reverse parse back into fields.
- Translation is a separate operation from creative prompt improvement. The
  implementation must choose and document a translation backend, its privacy,
  cost, offline behavior, and failure fallback before promising English output
  for arbitrary Russian text.
- Localization work in this phase means infrastructure plus all new or touched
  surfaces. A complete English translation of every legacy screen is a later
  release task.
- A provider-neutral generation and run-lifecycle contract must exist before
  Fal.ai is connected. Fal.ai must not deepen direct V3-to-`WorkerThread`
  coupling.
- A workflow-definition contract must exist before adding module-specific pages
  or Pinterest behavior. Clipart and Pinterest may share infrastructure but
  must not be forced into one prompt schema or one processing-control list.
- A step/output contract must distinguish generated artifacts, derived local
  exports, and external side effects. External delivery is never implicit in a
  generation or save action.
- The Fal.ai secret boundary is a release gate. The preferred production design
  is a server gateway that keeps Fal credentials off the desktop. Direct BYOK
  is allowed only as an explicitly documented interim mode with a clear risk
  decision and protected local storage; a plaintext `.env` is not an acceptable
  final design.

### Prompt requirements

- Accept Russian structured field input in the first implementation. Free-form
  Russian semantic parsing is a separate explicitly scoped feature.
- Store prompt data as structured fields, not only as one rendered string.
- Render a readable prompt with these sections: Object, Scene, Style, Color
  palette, Composition, Background, Details, Restrictions, and Technical
  requirements.
- Produce English provider prompts by default while keeping Russian UI labels
  and preview text available.
- Keep one visual direction across a series while varying pose, arrangement,
  or secondary details.
- Never silently invent a new subject, remove a restriction, or alter a user
  reference.
- Show the generated prompt before it enters the run plan and allow editing of
  individual prompts.
- Keep optional AI rewriting out of the mandatory path. If added later, it
  requires explicit user action, a visible before/after preview, bounded input
  and output, and a cost/privacy warning where applicable.

### Localization requirements

- Support Russian and English UI locales through a single translation layer.
- Keep UI locale, prompt language, provider model IDs, and internal status codes
  as separate concerns.
- Persist the selected UI locale and migrate missing locale settings safely.
- Use stable message IDs or Qt translation keys rather than scattering language
  decisions through workflow logic.
- Ensure provider errors, validation messages, diagnostics, and accessibility
  labels are localizable.

### Pinterest prompt generator — next implementation stage

Pinterest is intentionally a separate stage after Clipart and Fal.ai
acceptance. Its prompt schema is independent from Clipart and is prepared in
`pinterest_prompt_schema.py`. The schema is designed for vertical pins and
includes topic, object, background, text-safe area, headline, CTA, aspect
ratio, branding, visual hierarchy, style, and restrictions. It has its own
Russian/English renderer; it does not reinterpret or migrate Clipart fields.

The next implementation must add a Pinterest-specific input/preview page,
editable prompt entries, deterministic series generation, and capability-aware
provider rendering. The initial Pinterest workflow must not show Clipart-only
transparency or background-cleanup controls.

### Fal.ai requirements

- Integrate Fal.ai behind the existing provider abstraction and capability
  registry; the UI must not depend directly on Fal.ai endpoints.
- Verify the current official Fal.ai API contract before implementation,
  including authentication, queue/status behavior, cancellation, uploads,
  model identifiers, response formats, and pricing.
- Initially cover generation, image-to-image, background removal, upscaling,
  status polling, cancellation, retries, and cost estimation where the chosen
  models expose those capabilities.
- Keep model selection capability-aware: references, transparency, size,
  output format, and operation support must be validated before a paid run.
- Store no secrets in logs, prompts exported for support, tests, or release
  artifacts. Real provider tests require explicit cost approval.
- Treat provider profiles as `provider + endpoint/model + operation`, because
  alpha, input types, output format, limits, retention, and price can differ
  between Fal.ai endpoints.
- Define Fal.ai input retention and CDN handling before uploading user files;
  prefer no-store/short-retention settings where supported, download results
  before expiry, and document deletion limits.
- Record cost as a timestamped estimate with currency, model/profile, and a
  user-configurable maximum budget. An estimate is not a billing guarantee.
- Do not silently retry onto another paid model or fallback endpoint. Automatic
  retries must be bounded and idempotency/request identity must prevent a
  duplicate paid submission.
- Model cancellation honestly: distinguish `cancel_requested`,
  `cancelled_before_start`, `completed_after_cancel`, `already_completed`, and
  `cancel_failed`; a late result must remain traceable and no refund is implied.

### Out of scope for this phase

- Patterns and seamless-tile validation.
- Mockup generation.
- Invitation decomposition into layers.
- Canva integration or editable Canva templates.
- Module downloads, module purchases, and entitlement-based licensing.
- A mandatory AI prompt-rewriting request for every generation.

### Phase acceptance criteria

- A Russian user can create, inspect, edit, and save a structured clipart
  prompt series whose provider rendering is in English by default.
- Switching UI locale does not change the underlying prompt data or break old
  saved settings.
- Fal.ai models appear only for operations they support and are routed through
  one provider contract.
- Network-free tests cover prompt rendering, localization, provider payloads,
  errors, cancellation, retry behavior, cost boundaries, and secret redaction.
- A small approved live smoke test confirms at least one generation path and
  one processing path without turning paid calls into the test suite.
- Fal request IDs, late results, cancellation outcomes, and retry decisions are
  recoverable without resubmitting a paid task.
- Workflow-specific additional steps can consume validated artifacts and create
  PDF/Canva outputs or explicitly confirmed external deliveries without
  changing the core PNG pipeline.
