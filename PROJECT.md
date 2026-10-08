# Vibix Images

## Направление с выбором сценария, уточнение владельца 2026-10-08

Ориентир: Content Studio в TrendWatcher Video. Владелец поручил распространить
выбор направления с подходящими вариантами на весь конструктор, включая UGC,
каталожную и остальные виды съёмки. Последовательность: тип → направление →
сценарий; Изображение/Рилс определяет содержание сценариев. Шесть типов,
самостоятельная настройка, Далее и защита пользовательских полей сохраняются.
Конкретный новый макет утверждён владельцем: «хорошо, подойдёт».
Реализовано и локально проверено в текущей feature-ветке без выпуска обновления. Текущий статус:
STATE.md и docs/ui/3.1/composer-directions-20261007/README.md.

## Разделы конструктора промптов, утверждённая концепция 2026-10-07

Изображение/Рилс → раздел → сценарий. Разделы: Люди, Товары, Еда и напитки,
Интерьеры и архитектура, Животные, Природа и путешествия. Клипарт не включать.
Люди и Товары подробнее; UGC через конкретные сценарии. Человек допустим
в товарной съёмке. Шаблоны содержательны, редактируемы и сохраняют заданного
пользователем героя/товар. Концепция и конкретные макеты одобрены владельцем, с центрированием вкладок
Конструктор/Сохранённые промпты; реализация и локальные проверки завершены. План/статус: STATE.md и
docs/ui/3.1/composer-directions-20261007/README.md. Без платных запросов/сборки.


## Общие действия края и видимый расчёт, утверждено2026-10-07

Две общие иконки Чётче/Сгладить над кистью/пером. Реальное выделение точек
ограничивает действие соответствующим участком края, иначе весь край; активное
Лассо без выделения не ограничивает. Нижнее сглаживание убрать, Упростить
оставить для точек. Edge action применяется сразу, отдельный Undo, RGB и
явное SavePNG сохраняются. Группы Масштаб/Край/Инструмент/Контур; тонкие иконки,
tooltips<=2слов. Длительные contour/edge действия показывают indeterminate
indicator под изображением до commit/error/cancel; повторные запуски blocked,
отмена отдельная. Макет: docs/ui/3.1/edge-smoothing-20261007/final-*.png.
Пользователь поручил создание обновления, разрешены commit/push/Windows beta.

## Пошаговая резкость alpha, утверждено владельцем2026-10-07

«Сделать край чётче» сразу выполняет один существующий alpha-contrast шаг.
Повторные клики создают отдельные undo steps; при no-op кнопка disabled,
Undo снова делает её доступной. Удалить dedicated До/После/Применить только
этого действия; сохранениеPNG остаётся явным. Contour-local preview, RGB,
brush defaults и алгоритмLUT не менять. Выпуск требует отдельной команды.


## Точная кисть, запрос владельца2026-10-07

В общем редакторе прозрачности всех3модулей добавить настоящий1px и ряд
1–3–6–16–32–64 (последующее уточнение владельца: шесть размеров, без10px). Сохранить default16,
RGB, undo/redo и текущие способы сохранения. Для1px точечный stamp не растушёвывается.
Это расширение разрешённых controls; новая сборка/публикация требует отдельной команды.


## Выбор материалов и автоматический фон, owner-approved2026-10-05

Пользователь утвердил план доработки трёх сценариев auto-clipart/processing/clipart и затем полноэкранный макет двух списков «Цвет фона»/«Тип изображения». Это разрешает эти конкретные настройки сверх более раннего запрета новых controls в исследовании кромки. Поддержать opaque_clipart и legacy для полупрозрачных материалов; сохранить алгоритм/RGB, старые проекты/defaults, supplied alpha и generation provenance. Авто определяется по реальному supported-key источнику, explicit manual override не заменяет запись генерации. Белые/неоднозначные sources требуют проверки, универсальная matting accuracy не заявляется. Независимый оппонент, source/module checks и Windows-beta delivery входят в план; сборка запускается только по отдельной явной команде AGENTS, production publication не разрешена. КандидатStudio3.2.12, изменённые/зависимые modules1.5.3 minimumCore3.2.12. Windows/device acceptance остаётся обязательной после сборки.


## Cleaner automatic edge, owner-approved2026-10-03

The owner answered yes to accepting loss of the weakest semitransparent strokes
for a cleaner automatic edge. This supersedes mandatory retention of every weak
AA sample in the fully opaque generated-source automatic profile. Preserve source
files, established paint/core RGB, source-supplied alpha, legacy behaviour and
application/module compatibility. No new controls/settings, builds, network,
paid operations, downloads or dependencies. Use an independently implemented
bounded final edge selection after colour refinements; do not copy AGPL source.
Only low final coverage below half and existing background-dominated boundary
samples are eligible; stronger coverage and alpha255 remain protected. Diagnose
and report remaining coloured rim, detail loss and stair steps on actual images
before claiming quality. Mathematical low-coverage colour safeguards stay valid
before this explicit delivery selection. Existing manual editor remains separate.
For local post-cutout NN, use the preselection working alpha/RGB input and apply
the delivery alpha after NN. Transport alpha only in memory; preserve existing
hidden-RGB protection, stable API1 and old components without the optional hint.
Do not infer a recovered working matte from an already-cleaned saved PNG.

## Renewed automatic edge research, owner-requested2026-10-03

The owner requests stronger independent reasoning, an exact causal comparison
with the downloaded Clipbrook background-removal reference, and an automatic
source-level correction of coloured/dark rims. Reconsider assumptions rather
than treating the manual retouch as completion of automatic quality. Preserve
known paint/coverage, genuine outlines, fine geometry, source alpha and files;
the later owner-approved weak-edge tradeoff above governs final selection.
No new settings, builds, network, paid operations or downloads are authorized.
Reference behaviour may guide an independent implementation; the closed product
boundary below remains in force. Do not claim ideal edges or visual parity from
passing tests or source preservation. Retain historical failures and verify real
images before adopting a new candidate. Existing manual/editor and numeric v13
worktrees remain unchanged while this isolated investigation proceeds.


## Edge-quality and large-PNG correction, owner-authorized

Continue implementation without another task approval. Preserve source colours,
fine details and original resolution, including the owner's5016×5016 PNG.
Keep existing simple contour controls. On2026-10-02 the owner additionally approved
one optional «Сделать край чётче» action below zoom, with Before/After preview,
Cancel/Apply and a single undo step per application. It changes only alpha and
does not run automatically, recolour the image or add a strength control.
Contrast×2 can remove very thin geometry; mandatory preview is a deliberate
editing choice, not a guarantee of automatic preservation. Colour-rim correction
remains unresolved. No new colour controls are approved. Bound proposal
geometry and background jobs, preserve raw alpha outside local edits and keep
cancel/Undo/Redo/separate-copy save. The opaque-clipart ambiguity policy prefers
source paint over unsupported neighbouring-material fits. A supplied already
processed PNG alone cannot establish the original pre-cutout colour. Actual
intermediate generated/cutout/upscaled PNGs now establish the alpha restoration
ringing stage. Keep visible RGB exact when preparing temporary RGB-only upscale
input; use non-ringing alpha interpolation and preserve binary masks. Builds remain
separately authorized and are not part of this correction.

## Automatic Clipart deliverables, owner-requested2026-10-02

The section is named «Автоматический клипарт». Automatic collection runs and
restored/retried runs use transparent trim and300DPI final PNG metadata.
Remove fully transparent working margins before post-background upscale;
retain final trim after upscale/edge processing. Owner-approved2026-10-02:
after final trim, add a fully transparent border of1% of the trimmed object's
long side to every side, rounded up to a whole pixel (minimum1px). The border
is final canvas space, never softened object alpha or input to upscale.
Preserve source files and RGB,
explicit alpha-defined white paint, pattern/background canvas, and existing
custom processing choices outside the automatic workflow. Existing finished
files are not rewritten on reopening a project. DPI is print metadata, not a
request to resample pixels or trigger a paid operation.

## Automatic Clipart count correction and recoverable export

A changed requested count must update active objects and submitted jobs exactly.
Excluded ideas, recorded completed outputs and paid-stage evidence must remain
in the saved project. Returning to earlier steps does not erase ready work.
Cancelled or never-submitted ideas must not block export of ready PNGs; genuine
requested failures remain visible. Reusing outputs after replanning requires
unchanged prompt/settings provenance and the existing output-path checks.
The owner approved the export table and explicit partial-export UI on2026-10-02.
The table immediately persists membership; counts and Add set are at the top.
One ZIP action and explicit Save project remain. Ready-only export bypasses only
missing results, never ambiguity or invalid PNG preflight. Unfinished jobs remain
recoverable and require explicit confirmation before continuation. Existing user
set names are preserved; new standard set names are English. Approved/actual
safe-dummy screens: docs/ui/3.1/export-table-20261002/.

## Next-candidate preparation, owner-authorized2026-10-01

Prepare the agreed changes together in an isolated candidate branch and finish
safe source verification before any Windows build. Preserve source worktrees,
production data and existing beta releases. Local contour selection supports
lasso/Shift, magenta selection, independent Simplify/Smooth repeated small steps,
preview/cancel/apply and undo; no strength selector. Promotional signed cards
must share the adaptive fixed-size catalog and cannot grant access or run code.
The separate white-background hard-cutout mode preserves genuine white details
and needs independent subject segmentation; never globally erase white pixels.
Owner approved the white-method selector mockup2026-10-01. It reuses only
already cached U2Net, never starts a download from this method, and disables
Next for a missing model. New controls still require the project visual approval gate. Builds/publication
remain deferred; installed Windows acceptance cannot precede the build.

## Module action and responsive-card UX, owner-approved 2026-10-01

Use one primary action per module card without a dropdown: dark outlined Open;
turquoise outlined Download or Update when actionable. Highlighting itself must
not start downloads. Existing trusted entitlement/package checks remain required.
Keep card size349×248 and illustration height112px across normal/maximized windows;
center the grid and adapt columns to width. Owner approved the1920×1080 mockup.
Global transparency sliders remain deferred for discussion after offline quality
checks; diagnostic reference variants are not a production algorithm change.


## Direct transparency editing, owner request2026-10-01

Processing must allow opening selected existing PNGs directly in the transparency
editor without running the generation/processing queue. Return to the input
selection and save edits as a separate copy, preserving source files and module
access checks. Owner rejected a button beside file selection; the revised
left-navigation mockup is approved. Direct editing is implemented in the dedicated
feature branch; installed Windows acceptance remains pending. Global transparency
sliders and further edge/color algorithm changes are paused for owner discussion.

## On-demand Studio shell, owner-authorized 2026-09-29

Use source 6568fae (verified Windows 3.2.8) as the integration base. Studio is the
shell; Generation, Processing, Pinterest, Automatic Clipart and Prompt Composer
are separately downloaded signed modules. Preserve projects, settings, artwork
and compact-card image sizes. No purchase link: denied cards say «Нет доступа».
License refresh is automatic, no permanent status strip or refresh-access button.
Place «Обновления модулей» beside «Лицензия» in the top row.
Reuse the existing license server and exact signed rights; do not change server
code, deployments, bundles or customer grants. Owner subsequently authorized
publication of Studio and module release artifacts, plus temporary GitHub public
visibility solely for the Windows build with return to private afterwards.
Owner subsequently specified beta distribution for Studio3.2.9 and module1.5.0.
Prompt Composer requires its own
package and right; it is not implicitly included in Club/VIP.

## Processing method selection, 2026-09-29

Processing exposes the existing local neural models, cloud providers/models and
local chroma-key colour selector. The owner can choose the method explicitly;
background controls must not be unconditionally hidden in this workflow. This
restoration does not change automatic-generation UX or add a white chroma colour.
Processing offers Auto colour per imported image, respecting recorded generation
colour first and requiring review for uncertain backgrounds without neural fallback.

## Manual contour requirement, 2026-09-29

The transparency pen must create an outline directly by clicks, including on
opaque images. Double click closes it; closure alone must not edit pixels.
Explicit Remove inside / Keep inside actions preserve existing alpha elsewhere
without feathering. Point edits and applied masks support undo/redo; keyboard
zoom remains available. Material/texture is no longer a collection-wide UI field;
individual objects may describe their own materials.

## Transparency editor requirements, 2026-09-23

Owner approved one canvas with brush/pen tools, keyboard/mouse point editing,
brush diameters2/6/10/16/32/64px, default remove and85% hardness, color-only
background swatches. Autocontour supports up to4100px on each side, extracts
existing alpha (not RGB segmentation), and runs with application/cancellation
in a background worker. Cancelled or stale results must not change or save masks.


## Migration access policy, 2026-09-23

The public product name is Vibix Studio. Migration from Vibix Images3.1.4 retains
installer identity, existing storage, settings and license state. Club members
receive all workflows through their bundle; other customers retain individually
assigned rights. Upgrading the application does not itself grant extra modules.


## Approved Independent Components Target, 2026-09-23

Owner approved separating workflow planning/prompt rules from the Studio shell
and delivering one shared, independently updateable image-processing component.
Studio retains installation, application settings, credential access and job
orchestration. Workflow packages own their planning/prompt behaviour; the shared
processing component must not become a separate user workflow or three forked
algorithm copies. Verified loading and compatibility checks must precede use.
The source now implements this boundary; delivery requires the compatible Studio
bridge and service rollout described in docs/module-release-runbook.md. Component
updates use existing workflow update buttons, never an additional user-facing row.
Standalone admin-authored home news is independent of application/module releases.

Chroma preparation/removal is required for Automatic Clipart and remains available
for imported images in Processing. Whether ordinary Generation should retain
chroma or offer only online removal is still undecided; do not remove existing
capabilities or impose opaque-clipart prompt restrictions on general generation.


## Closed Product Boundary, 2026-09-22

Owner explicitly requires Vibix and its applications to remain closed-source.
No relicensing is authorized. Clipbrook output is the selected visual quality
reference for chroma removal; its AGPL source is not an authorized proprietary
runtime dependency or source translation. Implement improvements independently
and verify colour, coverage and small-detail preservation against real inputs
and known-truth fixtures. Passing tests alone does not establish visual parity.

## Optional Export Cleanup, 2026-09-20

Set export offers independent, default-off deletion of intermediate working PNGs
and generated originals. Cleanup follows successful archive publication and CRC
verification, applies only to tracked rough copies of exported results, and never
targets final PNGs, archives or user-imported originals. Untracked legacy files,
changed copies and unfinished/excluded items are retained. Choices reset after
each export. Cleanup failure must not report a successful export as failed.

## Opaque Clipart Material Policy, 2026-09-20

Owner detail-quality requirement, 2026-09-22: generated flowers, leaves and small
branches must remain readable and coherently formed, not smeared, fused or
translucent. Plan one appropriately framed asset per image; decorative use must
not shrink it to a miniature on the canvas. Preserve explicit element counts and
the selected style; soft styling describes colour/texture, not defocused edges.
Prompt compliance is not evidence of model output quality. Validate raw outputs
separately from removal/upscale; do not silently change paid model or resolution.

Automatic Clipart produces fully opaque illustrated subjects and details.
Collection planning and compiled prompts exclude glass, translucent petals,
see-through fabrics, smoke, mist and glow. Watercolor remains available as an
opaque painted texture. This restriction concerns the subject, not the transparent
PNG background, real openings between parts or boundary antialiasing. Translucent
material benchmark cases are not acceptance requirements for this module.

## Automatic Clipart Separation, 2026-09-19

Owner explicitly excludes collection planning, palettes/recipes, object/bundle
composition and set export from ordinary image generation. Those belong to the
separate `auto-clipart` module. Ordinary generation retains prompt input/import,
generation, processing and individual image editing; legacy `clipart` identifiers
and saved collection metadata are preserved for compatibility, not exposed as new
collection tools. Core module identity is now independent of its reusable legacy
state scope. Different module identities cannot bind the same scope in one live
shell or relabel each other's saved project envelopes. The separate built-in
automatic workflow now uses eight steps and restores its own saved runs and export
state. The workflow is available in the isolated Windows Test 3.2.1 installer and
as a signed 1.1.0 test-server module requiring that shell. This is not a customer
production release; owner acceptance and paid-provider gates remain in TASKS.md
and STATE.md.

## Acceptance Isolation, 2026-09-19

An explicitly requested acceptance build uses a compiled public-only profile,
separate application/storage/installer identity and independent test license and
publisher keys. Production has no runtime trust/endpoint override. Test installers
cannot replace a production executable; the CI installed smoke tests this guard.
The test service has its own database and exposes no administrator routes.

## Independent workflow delivery contract, 2026-09-19

Legacy generation keeps project/entitlement ID `clipart`; the separate
automatic Clipart catalog uses `auto-clipart`. Signed official workflow packages
may replace the three legacy and automatic Clipart built-in controllers through ModuleRuntimeHost,
without replacing the shell. Shared Core UI, project schemas and provider services
remain shell dependencies within the declared Studio compatibility range.
Remote release metadata is separately signed and exact module rights are checked
at manifest, download and runtime boundaries. Publisher package trust must be
provisioned independently of downloaded packages. The candidate shell pins a
dedicated publisher public key; private custody, draft-upload procedure and release
gates are in `docs/module-release-runbook.md`. Installed acceptance and production
rollout remain pending; current verification limits are in STATE.md.

## Portable PNG result-intent checkpoint, 2026-09-12

Generated PNGs now receive a hash-bound `.generation.json` schema-v2 sidecar that carries `result_kind`, stage (`raw`/`final`), optional chroma provenance and prompt SHA-256 without storing prompt text, credentials or local paths. The pending record is created before paid submission for every generated result; raw and final records are bound to actual PNG bytes. `stage` describes background-readiness rather than folder location: surface outputs are final, while Clipart is final only when the published PNG contains a meaningful transparent area (at least 4 near-transparent pixels and at least 0.1% of the canvas); isolated alpha noise does not qualify, and an opaque chroma Clipart remains raw so later removal can use its recorded color. Final records never return a chroma color for re-keying, and `stage=final` prevents automatic background removal from running again on a finished PNG. Re-imported PNGs can restore confirmed result intent; an explicit conflicting intent fails closed. Transparency edits rebind the record to new bytes and Contour copies inherit validated v2 lineage. Legacy schema v1 remains readable for chroma only and never invents a result kind. `ClipartRunRequest.worker_kwargs()` and `WorkerThread` normalization now preserve `chroma_key_color`, `result_kind` and `object_id` end-to-end. A final sidecar write failure after a paid image is already published is reported as a local warning rather than converting the paid generation into a retryable failure. Affected verification after independent review fixes: 257 passed, 1 skipped, 11 subtests; full isolated pytest: 1494 passed, 57 skipped, 2 deselected, 239 subtests in 64.86s. Independent review findings were verified and fixed: final schema-v2 PNGs cannot enter the legacy KIE remover path; raw-sidecar bind/cleanup failures after a paid generation no longer make the current run retryable; Transparency Editor commits PNG/mask/provenance in one recoverable transaction; and Contour Save As publishes PNG+sidecar recoverably. A second independent review of `0001da1..e73675a` found concurrency gaps in recovery/capture plus a stale-file lock. These are now closed by one OS advisory per-destination lock held across recovery, capture and commit; the lock is released automatically by the OS on process death, while a stale lock file alone never blocks later work. Planned raw/final pending/completed sidecar paths remain preflighted before the paid provider POST.

## Large AI-planning batches checkpoint, 2026-09-12

Clipart OpenRouter planning no longer hard-stops above 80 target ideas. A single owner-confirmed planning attempt is split deterministically into sequential requests of at most 80 targets; the confirmation shows total ideas, request count and a combined estimate before any paid POST. There are no hidden retries. Successful earlier batches update only a private working recipe so later batches can see prior proposed names/actions and avoid cross-batch duplicates; the editor/project remains unchanged until every batch succeeds. Any batch error/cancel/stale-state leaves the collection unchanged while clearly warning that already-sent requests may still have been charged. Reference-image consent, fingerprints and capability checks remain unchanged and, when opted in, the confirmation explicitly states that references are sent in each batch. Focused planning/OpenRouter/builder verification: 54 passed + 13 subtests; full isolated pytest: 1460 passed, 57 skipped, 2 deselected, 235 subtests in 64.42s. No live paid batching request was made.

## Wreath/frame interior-opening QC checkpoint, 2026-09-12

Final Clipart PNG preflight now uses recipe `object_id`/role to enable an extra local Review check for wreaths and frame-like borders. A bounded 256×256 alpha preview accepts meaningful transparent center space (including an intentionally open wreath) or a significant enclosed transparent region. Missing/filled interior space is a Review reason, not a hard blocker; hero/decor outputs are not subjected to this rule. The check is read-only, makes no provider call and does not alter PNG bytes. Labels remain separate future semantics rather than inheriting wreath rules. Focused alpha/results/export verification: 102 passed + 5 subtests; full isolated pytest: 1457 passed, 57 skipped, 2 deselected, 235 subtests in 63.54s.

## Commercial Clipart prompt guidance checkpoint, 2026-09-12

Clipart planning now has a deterministic collection-first commercial guidance layer derived from owner-provided Etsy bundle/prompt material as structural inspiration, not copied prompt templates. The planner explicitly asks for commercially useful roles, no filler, controlled variety and no near-duplicates while preserving one style/palette direction. Final object prompt compilation adds local cutout-quality guidance (full visibility, safe margins, readable silhouette, no crop or accidental extras) plus role-specific constraints for compositions, wreaths, borders and decor. These rules do not replace the internal transparent-background/chroma contract and make no provider call. Future backlog keeps Lettering, Prompt Doctor and Etsy/Pinterest/listing-cover strategy separate from the active Clipart module; the durable roadmap is `FUTURE_STUDIO_MODULES.ru.md`. Focused prompt/planner verification: 70 passed + 23 subtests; full isolated pytest: 1453 passed, 57 skipped, 2 deselected, 235 subtests in 64.65s.

## Reference-image consent/handoff checkpoint, 2026-09-12

Clipart AI planning can now optionally send selected reference images to OpenRouter vision-capable models. Image transfer is opt-in per reference, disabled by default, one-shot only, and never persisted as project permission. Before a paid request the app validates file format/size, fingerprints the exact selected bytes with SHA-256, checks the live OpenRouter model catalog `input_modalities`, then shows a second confirmation listing the selected filenames. The fingerprint is checked again immediately before network handoff, so replacing a file after consent stops the request. Up to 4 PNG/JPEG/WebP references may be selected, max 10 MB each and 20 MB total. Local paths are never sent to the model; the request contains bounded base64 data URLs plus explicit roles/notes, and image requests set OpenRouter `data_collection: deny`. KIE remains text-only until its multimodal envelope/pricing are separately verified. No live paid image-reference request was made in this checkpoint. Real Qt proof: `docs/ui/3.2/reference-image-consent/actual-reference-consent-1120x780.png`. Focused affected verification: 60 passed + 13 subtests; full isolated pytest: 1448 passed, 57 skipped, 2 deselected, 235 subtests in 64.95s.

## Clipart PNG quality preflight checkpoint, 2026-09-12

Set export now performs a local read-only preflight of final transparent Clipart PNGs.
It explains specific problems per design and separates hard blockers (unreadable, no
transparency, nearly empty) from review warnings (canvas-edge contact, excessive
semitransparency, likely colour fringe). Blockers prevent ZIP creation only while the
design remains included; the user can open the existing transparency editor or exclude
the design without deleting the PNG. Background/surface outputs are exempt from alpha
requirements. The check does not modify files, call providers, or trigger paid retries.
It is intentionally lighter than the formal VS-03/VS-18 numerical edge-QC profile.
Real Qt proof: `docs/ui/3.2/alpha-qc/actual-alpha-qc-1120x780.png`. Verification:
focused 118 passed + 5 subtests; full isolated pytest 1431 passed, 57 skipped, 2
deselected, 233 subtests.

## Bundle regression checkpoint, 2026-09-12

Cross-cutting regressions now explicitly prove that one PNG can participate in four
commercial sets without multiplying paid generation or processing quantities. Existing
coverage already verifies membership migration/roundtrip, independent manual set
inclusions/exclusions, current-run seeding, ambiguous-variant blocking and hidden
background implementation terminology. Focused: 28 passed + 5 subtests; full isolated
pytest: 1416 passed, 57 skipped, 2 deselected, 233 subtests in 64.49s.

## Style Profiles checkpoint, 2026-09-12

Clipart now has a local Style Profile layer. A collection has one base visual style
plus optional character modifiers; recommendations are deterministic from theme/context
and never trigger a provider call. The library is brand-neutral and supports custom
user wording. Selecting a profile compiles a stable provider-facing style phrase while
keeping the user-visible recipe fields round-trippable. Planning receives the same
style guidance alongside Holiday Profile and palette context.

The approved production UI is implemented with 3 recommendations, compact featured
styles, category filtering, multi-select modifiers and preserved advanced visual fields.
User-provided style guides were used only as classification/UX inspiration; concrete
brand-specific style names and third-party prompt templates are not copied. Plan:
`docs/superpowers/plans/2026-09-12-style-profiles.md`. Real Qt proof:
`docs/ui/3.2/style-profiles/actual-teddy-christmas-1120x780.png`. Focused verification: 46 passed + 11 subtests; full isolated pytest: 1415 passed,
57 skipped, 2 deselected, 233 subtests in 64.28s.

## Transparent-background UX checkpoint, 2026-09-12

Clipart and Processing now hide the implementation of transparent-background
preparation from user-facing controls, previews, prompt review/editing, CSV export and
runtime errors. Technical color selection and removal provider/model choices remain
internal and compatible with existing drafts. User-visible wording describes only the
result (prepare transparent background, check edges). Hidden generation suffixes remain
attached internally when a prompt is edited, so UI simplification does not change the
actual processing contract. Verification: focused 191 passed + 5 subtests; full isolated
pytest 1402 passed, 57 skipped, 2 deselected, 233 subtests in 61.21s.

## Holiday-aware Clipart checkpoint, 2026-09-12

Clipart now has a local Holiday Profile layer and curated five-color palette library.
Holiday context enriches palette, character accessories, props, decor, compositions,
mood and background hints without replacing the main theme or triggering a paid call.
First wave: Christmas, Halloween, Easter, Valentine’s Day, Thanksgiving, 4th of July /
Independence Day, St. Patrick’s Day, Baby Shower, Birthday, First Birthday. Mother’s
Day/Father’s Day are deferred. Christmas and Halloween use explicit canonical holiday
color logic. Builder recommendations are local/deterministic and cards show exactly
five swatches; custom and reference-derived palettes remain available.

`Holiday PRO Prompt builder.xlsx` was reviewed as structural inspiration for holiday,
objects/details, emotion, activity, background, palette and preset dimensions; it is
not copied as an implementation template. Implementation plan:
`docs/superpowers/plans/2026-09-12-holiday-aware-clipart.md`. Focused verification:
35 passed + 11 subtests; full isolated pytest: 1403 passed, 57 skipped, 2 deselected,
233 subtests. Real Qt proof: `docs/ui/3.2/holiday-palettes/christmas-1120x780.png`.

## Current handoff, 2026-09-11

Historical handoff, superseded by the approved2026-10-02 table above.
Automatic set export UI was summary-first. The main screen shows only unique
PNG count and dynamic set count, proposed-set cards and `Создать наборы`; the
manual membership matrix opens only via `Изменить состав наборов`. The old
confirmation checkbox, technical PDF/manifest wording and redundant Close action
are removed. Manual headers/checks are centered, `К наборам` fits its label, and
hovering a filename shows a bounded PNG preview beside the cursor.

Bundle-result review is wired to the current run: missing object results and
multiple successful variants are reported, never auto-selected, and block export
until reviewed. Independent review of `3d48468` found three P2 state/counting
problems; all are fixed in `5688c1a`, including unique-path ambiguity counting,
saved-only export state, and clearing a resolved ambiguous choice while missing
results stay blocking. The UI accepts arbitrary set counts.

Planner schema v2 adds deterministic thematic sets alongside nested commercial
tiers: a balanced 30-image collection yields 6 useful sets and larger collections
can yield 7-8. Legacy v1 plans remain valid and migrate without changing commercial
set IDs; replanning preserves stable IDs and user titles. No provider or paid call
is involved. Combined final regression: 1390 passed, 57 skipped, 2 deselected,
233 subtests; local read-only diff review found no new P1/P2. Real 1120x780 Qt proofs are under `docs/ui/3.2/auto-set-export-proposal/`.
No build, paid API, workflow dispatch or deployment.


Many-to-many export membership завершена после preservation commit `40ceffa`.
Legacy `path -> {title, included}` мигрирует в version 2 со стабильными asset/set
ID; один PNG может входить в несколько комплектов независимо, contour-copy
сохраняет memberships, а первый overwrite legacy-файла создаёт точный backup.
Исправлена обработка ошибки backup в standalone draft.

Проверка: focused 31 passed + 8 subtests; полный isolated pytest 1369 passed,
57 skipped, 2 deselected, 228 subtests; py_compile и git diff --check проходят.
Финальное независимое read-only ревью не выявило P1/P2 findings.

Автоматическое планирование mini/standard/maxi/full-bundle теперь выполняется
до prompt handoff по стабильным object ID. Уровни строго вложены, role-aware и
адаптируются к размеру коллекции; set ID сохраняются при пересчёте и roundtrip.
Проверка increment: 32 focused passed + 4 subtests; full isolated pytest 1372
passed, 57 skipped, 2 deselected, 232 subtests; independent review без P1/P2.

Связка сохранённого Bundle Plan с результатами теперь выполнена: внутренний
`object_id` проходит через PromptEntry, все проверенные пути редактирования,
run queue и retry, но не отправляется во внешний provider payload. Перед экспортом
успешный уникальный PNG текущего запуска получает все memberships из плана;
ручные назначения не перезаписываются, а несколько успешных variants одного
object ID считаются неоднозначными и автоматически не выбираются. Один PNG
переиспользуется в нескольких ZIP без повторной генерации/обработки.

Проверка increment: focused 204 passed + 27 subtests; full isolated pytest 1377
passed, 57 skipped, 2 deselected, 232 subtests; финальное независимое read-only
ревью после исправления двух P2 потерь object_id: NO P1/P2 FINDINGS.

Следующая задача строго по порядку: убрать ручную таблицу из обязательного пути
и оставить её как необязательное «Изменить состав наборов», затем расширить
палитры и провести пользовательский UX-аудит терминов.

## Active 3.2 development scope

Latest owner decisions (supersede the manual-first export workflow): minimize
manual work throughout. User supplies creative direction, reviews the proposal
and corrects exceptions. Plan mini/standard/maxi/full-bundle membership before
generation; one asset may belong to several sets, generated/processed once and
reused in each ZIP. Default nested tiers are proposed automatically; manual
membership editing is secondary. Count unique generated assets separately from
total delivered files. Preserve explicit paid-launch approval and quality checks.

Expand palette cards (5–7 actual swatches) by holidays, seasons, nature, color
families and use; recommend by brief before showing the full library. Nature
includes mountains, sea, forest, sand, clay, flowers, berries and fruit. Keep
custom/from-reference palettes and collection-wide consistency.

Background-removal technique, technical key color and names such as chroma-key
must NEVER appear on user-facing screens, settings, tooltips, errors, progress,
help, user diagnostics or delivery metadata. Only result-oriented language
(transparent background, check image edges). Internal developer documentation
and diagnostics may retain implementation details; this does not hide text/image
generation provider/model choices or costs. These refinements are pending code.

Approved text assistant: support both KIE and OpenRouter, either key sufficient.
Selected models: Gemini 3.8 Flash, DeepSeek V4 Flash Vision Exp (experimental),
GPT-5 mini (not GPT-5.4 mini). Provider/model is independent of image generation.
Only confirmed routes are offered: KIE Gemini; OpenRouter all three. One explicit
request through one service, no silent provider/model fallback or double spend.
Model availability and prices must be checked per service; no universal aliases.

Owner-approved refinement: automatic set planning is the primary Clipart path.
Users specify theme/purpose/context, characters/motifs, visual direction,
palette/references and quantity. The app proposes individual objects, actions
and details; manual item editing is optional. Recipe allocation alone is not AI
planning. Users review before image spending, pin ideas, replace one or regenerate
unpinned ideas. No automatic paid generation on draft load or navigation.

Owner clarification: Clipart, Patterns and Junk Journal are separate application
modules with their own entry points, screens and workflows, not product-type
tabs in one universal builder. The owner rejected the mixed result-kind mockup.
Shared palettes/presets/providers are internal reusable services. Modules set
technical result_kind; do not expose it as a cross-module per-row selector.
Clipart is first, Patterns next, Junk Journal a separately scoped future module.

Owner-approved Clipart prompt direction, consolidated 2026-09-10: a builder
with Holiday themes, conditional character fields, editable versioned presets,
palette sources and distinct combined-details versus separate-variants modes.
No Midjourney integration; retain existing KIE/fal.ai workflows. Reference
builders inform our own implementation, not wholesale reuse of their assets.
Junk Journal is an owner-approved separate future module for coordinated pages,
papers, cards and decorative elements; preserve product backgrounds and reuse
shared palettes/presets/references. Page/export specifics remain to be scoped.
Alphabet remains future scope. Patterns retains local
composition and AI-tile paths; Nano Banana Pro is a comparison candidate, while
SeedVR2 Seamless is an optional tile-upscale candidate, not a tile generator.
See PRD v2 and its task list for acceptance and the ordered next increment.

Owner approved the attachment review follow-up on 2026-09-10: compare local
cutout candidates and continue implementation. Preserve and extend the existing
alpha-reuse path; generation capabilities belong to the actual provider/model,
not the model family name. KIE remains the GPT integration route. Native alpha
and chroma converge on common final review/export. White removal remains an
experimental candidate; difference matting is not a default. Details and measured
candidate rejection: docs/research/attached-pipeline-review-2026-09-10.ru.md.
The attachment's implementation prompt is research input, not project authority.

Approved home: three recently saved projects above an equal-sized illustrated
module catalog. All projects are retained, with autosave and explicit resume;
reopening must never resubmit paid work. Module actions: Open/Update,
Download if entitled, Buy if not entitled, Coming soon if not released.

Product clarification, 2026-09-08: Studio is a modular seller workspace, not a
replacement of the app with Auto Clipart. Preserve standalone universal image
generation and processing. Product modules cover an idea-to-deliverables workflow;
future directions include mockups, tumbler designs, Excel products, listing/SEO
preparation and separately confirmed publishing. Package downloads and execution
require module-specific license rights; unavailable modules show promotional
cards. Existing Pinterest is to become an independently updated module before
its later board/description/content-plan expansion. Compatible new modules must
register without editing the shell. Future directions are not all 3.2 features.

The owner authorized Studio 3.2 implementation on `develop/3.2` from the 3.1
runtime baseline. See `PRD_VIBIX_STUDIO_3.2_V2.ru.md` and
`TASKS_VIBIX_STUDIO_3.2.ru.md` for installable official modules, automated
Clipart sets, local contour/alpha editing, Patterns, meaningful output names
and Letter contact sheets. This supersedes the historical deferral of Patterns
below for this new branch only. Stable 3.1 workflows remain unchanged.
New UI requires the repository's visual approval gate. Backend prototypes are
not a completed 3.2 application, and no release/version metadata is bumped yet.

## Purpose

Windows desktop application for generating and processing clipart images. The project supports KIE-backed generation and local or remote processing providers, including Real-ESRGAN, rembg, BEN2, PhotoRoom, metadata cleanup, and bounded provenance inspection.

## Runtime

- Python 3.11+; the current Windows environment uses Python 3.12.
- Runtime dependencies are in `requirements.txt`; development checks are in `requirements-dev.txt`.
- The application is PyQt6-based. Linux GUI checks should use Qt offscreen mode.
- Node.js is not a project runtime requirement.

## Standard commands

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m py_compile main.py
QT_QPA_PLATFORM=offscreen python -m unittest discover -s tests -v
```

Windows activation is `.venv\\Scripts\\Activate.ps1`.

## Workflow boundary

Development is VDS-first. `develop/3.1` is the current integration line for
3.1.0; frozen 3.0.x and old release-candidate branches are historical and must
not be used as implementation bases. Windows remains the clean clone for
Windows-specific behavior and visual checks. GitHub is the only handoff point;
do not edit the same branch from both machines simultaneously.

## Sensitive data and artifacts

API keys, credentials, `.env` files, user configs, generated images, build outputs, model binaries, and release installers are local-only and must not be committed. See `VDS_WORKFLOW.md` for the transfer procedure.

## Current product state

The ordered MVP and cleanup acceptance work is complete. The product is branded
as `Vibix Images` with the subtitle `AI Image Generation & Processing`; the
approved shared mark is integrated into the runtime and Windows packaging
configuration. The self-hosted license
service is deployed, and the desktop client uses signed online validation with
a bounded seven-calendar-day offline grace for a previously verified license
during transport or server outage. First activation, explicit denial,
revocation, expiry, tampering and clock rollback remain fail-closed. The main
interface stays closed until online validation/new activation or a valid signed
local proof within that grace.
The first screen exposes safe license status, license replacement, and API
settings. New projects use a Pictures-based default and retain the last selected
work and result folders in user-data preferences.

A replacement Windows installer was built successfully on 2026-08-15 from
implementation commit `43682ac` in GitHub Actions run `31909510317`. The packaged
executable passed startup-license, first-screen license/API control, signal
connection, and Pictures-default smoke checks before Inno Setup created the
installer. Its SHA-256 is
`b228999e36029bf91f3a5cbf307422f557cfb28ed2b4c86b6b3848c7a0d1ea6d`.
The legacy GitHub updates flow remains superseded and is not an active delivery
channel. A licensed V3 update client and a bounded user-facing diagnostic
journal are implemented on `codex/feature-updates-diagnostics`. The client asks
before downloading, downloads only after consent, verifies the signed manifest,
size, and SHA-256, and then launches the Windows installer. The corresponding
private-artifact delivery is implemented in the license-service repository on
`codex/feature-secure-updates`. Migration 006 and that server branch were
deployed to the existing public staging-like service on 2026-08-16; its health,
artifact-upload UI, and license-signed update-key delegation were verified.
The Windows-only `3.0.1` build completed successfully in GitHub Actions run
`31924194111` on 2026-08-16. The packaged entrypoint verified the internal
`3.0.1` version plus the license, diagnostic, and update wiring before Inno
Setup created the installer. The downloaded installer SHA-256 is
`e095a018a0dd44d7f9d99c7d4bba7e35a7519974894f0428d957c51c40beb973`.
The current Windows installer naming convention is
`VibixImages-Setup-<version>.exe`. GitHub Actions run `33002277766` built the
approved three-stage Polar dark installer for version `3.0.5` from merged
`develop/3.0` commit `631219f1b2494857d82f07a380e2f6cf538a4f02`. The workflow
installed the finished package and verified the application artwork and prompt
screens from the installed copy. The installer SHA-256 is
`fceb6abfb44c2feb93ce8f2e2142987dc551fa47b0ddf1d7667341b6f12e8fef`.

## Next product phase — generation quality and provider expansion

Version 3.0.7 is the frozen baseline for the next product phase; new owner
feedback does not expand that release. The authoritative 3.1.0 delta is
`PRD_3.1.ru.md`, and its ordered implementation source is `TASKS_3.1.ru.md`.
The `Next Product Phase` section in `PRD.md` and `NEXT-TASK-*` history in
`TASKS_3.0.ru.md` remain architectural background only where they do not
conflict with those 3.1 documents. The phase is a focused improvement of the
existing generation and processing workflows:

1. establish workflow composition and a structured clipart prompt contract;
2. prepare localization infrastructure for Russian and English versions
   without coupling UI language to prompt language;
3. choose the translation backend and make the clipart prompt generator produce
   coherent prompts from structured Russian fields;
4. establish a provider-neutral generation/lifecycle contract before adding a
   new provider;
5. add Fal.ai through the provider abstraction for confirmed operations;
6. validate the complete clipart workflow before designing the Pinterest prompt
   generator.

The default policy is to build prompts deterministically from structured fields
(`Object`, `Scene`, `Style`, `Color palette`, `Composition`, `Background`,
`Details`, `Restrictions`, and technical requirements). Optional AI prompt
rewriting may be added later, but it must be explicit, previewable, bounded by
cost and length, and must not silently change the user's intent.

The application should store clipart prompt data structurally and render it
separately for the UI and for providers. Free-form Russian-to-English
translation is an explicit architecture decision and must not be faked by
merely adding English section labels around Russian text. An English UI will
reuse the same data model and provider contracts. Patterns, mockups,
invitations/Canva, and module-based licensing are intentionally deferred until
the core clipart and Pinterest workflows are stable.

The phase also introduces a workflow-definition layer before new page-specific
features are added. A workflow can reuse shared pages, provide its own prompt
builder, and decide which processing operations and provider controls are
relevant. A capability with no user value must be omitted from that workflow,
not shown as a disabled checkbox. This is internal product architecture; it is
not yet commercial module licensing.

Workflow definitions may also add ordered post-processing and delivery steps.
One workflow may end with a PNG, while another may create a PDF, prepare a
Canva-compatible package, or upload an approved result to Google Drive. Local
file creation and external delivery are separate step types; external actions
require an explicit confirmation and a visible destination before execution.
