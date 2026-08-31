# Project state

Updated: 2026-08-31

## Unified bounded diagnostics — 2026-08-31

The owner approved one visually persistent `Диагностика` action at the top
right. The duplicate Results-page technical-log button/dialog is removed; the
top action opens the same application journal before mode selection and inside
the wizard. That journal already correlates application, licence, workflow,
run/item/stage, provider, retry/cancel, update and export events.

The audit confirmed that byte-only retention could keep about 22,000 small
events in one 8 MiB session and allocate about 40 MiB while reading it. It also
confirmed that once the byte cap was reached a later provider error was lost,
and that the emitted KIE/Fal `provider_task_recovery_deferred` event was rejected
by the structured allow-list. The journal now retains at most 5,000 events per
launch and reads at most that many from each of the newest three launches,
including oversized legacy files. Repeated polling keeps the first sample,
state transitions and every tenth sample. Normal events stop before the hard
limit, reserving 1,024 event slots and a bounded byte tail for warnings, errors
and run/session terminal records. Deferred recovery is a warning with safe
provider/model/task context; API settings record only configured booleans for
KIE, PhotoRoom, Fal and RunPod. Prompt, credential, image, URL and private-path
exclusions are unchanged.
Fal generation and processing now publish the lifecycle information already
returned by their existing calls: accepted submission, sampled status changes,
provider success and bounded wait/HTTP failure. No availability probe, retry or
additional paid request was added; a recoverable polling outage remains the
separate `provider_task_recovery_deferred` warning.

Verification is green: the focused diagnostics/Fal/UI suite passes 208 tests
and 24 subtests; the full offline suite passes 1049 tests and 146 subtests,
with 57 documented platform/deferred skips and two intentional deselections.
The bounded-journal benchmark retained the late provider error and terminal
records while reducing peak legacy-read memory from about 40.7 MiB to 6.46 MiB.
The fresh automatic Chroma benchmark also passes: alpha IoU `0.968704`, alpha
MAE `0.018194`, median 2048×2048 runtime `1.400 s`, peak RSS `420.824 MiB`
below the `448 MiB` ceiling. Compilation, sensitive-artifact scan,
`git diff --check` and final independent review pass. Manual Windows UI and one
controlled live Fal run remain release-acceptance checks.

## Windows acceptance regression: 300 DPI hidden — 2026-08-30

The owner confirmed that `Установить 300 DPI` is absent from both Clipart and
Processing in the current Windows candidate. This is a real UI/state regression,
not an intentional product removal: DPI writing, final-save verification,
project state and runtime stages remain implemented.

The root cause is the workflow contract introduced by commit `5163b1e`:
`_CLIPART_OPERATIONS` omits `export_300_dpi`, and both Clipart and Processing
reuse that allow-list. `ProcessingPipelineEditor._apply_workflow_visibility()`
therefore hides the existing checkbox and resets an already enabled value to
`False`. A direct offscreen reproduction confirms `allowed=False`,
`hidden=True`, `state=False` in both modes. Existing DPI tests exercised the
editor/runtime without this workflow boundary and did not detect the omission.

The regression is fixed on `codex/fix-3.1-windows-acceptance-blockers` by adding
the existing operation back to the shared workflow allow-list. A workflow-level
offscreen regression proves that Clipart and Processing both expose the control
and preserve an enabled value; the focused workflow/editor/final-save suite
passes 28 tests. Replacement Windows acceptance remains required before release.

## Windows acceptance regression: failed KIE item shown as information — 2026-08-30

During a two-item KIE generation with the valid documented model
`flux-2/flex-text-to-image`, item 2 returned terminal provider error `422` and
the generic provider message asking to retry or change the input/prompt. The
single response does not identify whether the cause was transient provider
failure or that particular prompt; no automatic or additional paid retry was
performed.

The journal then displayed `Уровень: информация`, event `item_finished` and
`Обработка изображения завершена.` while retaining the failure text. This
misclassification is reproducible from source: the worker emits
`item_finished` with `outcome=failed`; event severity is inferred only from an
event name ending in `_failed`, and the journal summary is selected from the
generic `item_finished` label without considering outcome. Provider failure
itself is already recorded separately as `provider_task_failed`.

This diagnostics defect is fixed on the release-blocker branch. Any structured
event with `outcome=failed` is forced to error severity, and failed
`item_finished` receives the unambiguous summary
`Обработка изображения завершилась с ошибкой.` Existing provider/task/model,
stage and bounded error fields remain available. The new builder and persisted
journal regressions first reproduced the old info/success wording and now pass.

## Windows acceptance regression: Fal.ai HTTP 405 across models — 2026-08-30

The owner reproduced the same terminal `Fal.ai HTTP 405` during generation with
two independent Fal.ai models: `fal-ai/flux/schnell` and
`ideogram/v4/fast`. Both items in both runs failed identically. This cross-model
reproduction makes a model-specific outage or bad prompt unlikely and points to
the shared Fal request lifecycle in the current Windows candidate. Both failures
are also rendered through the already confirmed misleading `item_finished`
information-level event.

The exported full diagnostic sequence narrows the failure boundary. Fal accepts
each POST submission and returns a distinct request ID; the application records
`provider_task_submitted`, then fails before the first
`provider_task_polled`. The 405 is therefore not a submit rejection and occurs
during the first lifecycle read. If the first status is already `COMPLETED`, the
old event order also permits the failing read to be the result URL, so the
archive alone cannot honestly distinguish status from result. Official Fal
queue documentation returns provider-supplied `status_url`, `response_url` and
`cancel_url`; the candidate discarded all three and reconstructed them from the
model and request ID.

The fix branch now validates, uses and journals Fal's exact lifecycle URLs for
generation and processing, including restart recovery. Only HTTPS URLs on
`queue.fal.run` containing the same request ID are accepted; cross-host,
downgrade and mismatched-task values are rejected, and old journal records keep
the backward-compatible reconstructed fallback. The focused Fal/KIE/concurrency
and redirect-security suite passes 116 tests. This removes the confirmed client
contract defect without another paid submission; one controlled Windows Fal
run remains necessary to prove that the observed provider-side 405 is gone.
Final review also reproduced a cancel-recovery double read: accepted HTTP
400/404 bodies were consumed while extracting an error detail and then parsed
again as empty. The response is now bounded and parsed once, so
`ALREADY_COMPLETED` remains a valid late-cancel outcome.

The same report exposes a separate diagnostics defect:
`v3_run_queue._provider_model_routes()` hard-codes `generation:kie` for every
generation run, so both Fal runs are incorrectly announced as KIE even though
their model and actual worker are Fal. This does not cause HTTP 405, but it makes
provider preflight, cost interpretation and support evidence misleading.

The fix branch now derives the generation provider from the actual text or
reference model used by each run item. Fal-only, KIE-only and mixed KIE/Fal
batches have separate regressions, including a Fal model ID without the
`fal-ai/` prefix.

Further paid Fal.ai attempts remain stopped until the source gate and review are
green and the owner separately authorizes a controlled acceptance request.

## Windows acceptance evidence: KIE GPT Image 2 succeeds — 2026-08-30

The owner supplied the sanitized run report and full diagnostic package for a
successful `gpt-image-2-text-to-image` KIE run. Two prompts produced two distinct
KIE task IDs; both submissions returned HTTP 200, both tasks reached `success`,
each downloaded exactly one PNG, Local Chroma Key completed, and the run ended
with `succeeded=2`, `failed=0`. The ready filenames are distinct. This evidence
confirms that KIE credentials, submission, concurrent polling, result download
and final export work in the same Windows candidate, and that the earlier
`flux-2/flex-text-to-image` 422 is not a candidate-wide KIE integration outage.

The report alone does not provide pixel-level transparency quality evidence or
filesystem hashes, so it does not close Chroma fidelity or duplicate-content
acceptance. It does confirm that this run did not create duplicate task IDs or
duplicate ready filenames.

## Windows acceptance regression: duplicate/mislabelled rough stages — 2026-08-30

The owner supplied all six PNGs published to `rough/` by the successful
two-item KIE GPT Image 2 run. Hash and decoded-pixel comparison proves that the
five files labelled `rough_*_generated.png` are only two unique provider
results: `rough_01_generated` and `rough_04_generated` are pixel-identical
raccoon images; `rough_02_generated`, `rough_03_generated` and
`rough_05_generated` are pixel-identical ballerina images. The KIE lifecycle
still contains exactly two paid task IDs, so this is not repeated paid
generation.

The root cause is `_persist_rough_outputs()`. It classifies every raw PNG by a
substring search, with the generic marker `gen` falling back to stage
`generated`. Pipeline files keep `gen` as their item prefix, so
`gen_metadata_*` and `gen_existing_alpha_*` are incorrectly republished as new
generated images. In this run, the exact mapping is the original two downloads,
two metadata-cleaned copies and one existing-alpha copy, plus the correctly
labelled raccoon `bg-removed` stage. The current tests assert that rough files
exist and use collision numbering, but do not require one published generated
stage per actual provider result or reject semantic duplicates.

This confirmed file-publication regression is fixed without changing the
approved `rough/` and `output/` folders. The `generated` classifier now accepts
only the exact provider-download filename for the current run; metadata-cleaned
and existing-alpha copies are no longer relabelled as new generations. A
five-file reproduction now publishes exactly two generated stages and one
meaningful background-removal stage, and the focused output-path suite passes.

The same pixel evidence resolves the blue-background question. The raccoon KIE
download is an opaque RGB image with the requested blue background, and Local
Chroma Key produces the separate alpha result. The ballerina KIE download is
already RGBA with usable transparency before background removal; KIE did not
follow the requested blue-background instruction for that item. The application
then correctly follows the existing `skip_remover_for_alpha` rule and preserves
the provider alpha instead of running Chroma. The UI/journal should make this
decision visible, but flattening valid provider alpha onto blue is not approved.

The owner verified the KIE account history and confirmed exactly those two paid
tasks. The supplied ballerina request also removes payload ambiguity: its inner
prompt is exactly 1301 characters, matching `item_input_inspected`, and the
request uses `aspect_ratio=1:1` and `resolution=1K`. Source inspection confirms
that the GPT Image 2 payload contains only those documented fields and does not
request a transparent background. The prompt repeatedly and unambiguously asks
for an edge-to-edge opaque blue canvas; therefore the provider result failed
that prompt constraint. A Chroma acceptance run must report this source as
inconclusive/skipped rather than count provider alpha as evidence of Chroma
quality, and it must not perform an automatic paid regeneration.

## Windows owner feedback follow-up — 2026-08-31

The owner has started manual Windows acceptance. The current source follow-up
implements the small, approved UI corrections without changing provider
runtime contracts:

- mixed pipelines now show separate `KIE`, `Fal.ai` and optional `PhotoRoom`
  rows plus `Итого`; Fal.ai refresh changes only its row and an incomplete
  subtotal is never presented as a complete total;
- CSV export now has a separate `Экспорт:` group with a visibly
  labelled turquoise-accent `CSV` button and an explicit tooltip/accessibility
  name;
- `Апскейл после удаления фона` is temporarily hidden and normalized to off in
  both Clipart and Processing UI. Its implementation remains intact for the
  future alpha-safe endpoint; all other operations, including first upscale and
  `Экспорт 300 DPI`, remain visible and functional.

The following product improvements remain deliberately deferred:

- Fal.ai ESRGAN is correctly blocked after background removal because its
  official contract supports PNG but does not guarantee alpha preservation.
  Fal.ai now documents a separate `topaz/upscale/image/transparent` endpoint
  that preserves alpha end-to-end and always returns PNG at a fixed, billed 4×
  scale. Task 29 records it as the preferred next-version after-removal model;
  ESRGAN remains a before-removal option unless separately proven alpha-safe.
- a complex multicolour subject demonstrated that no single blue/red/green key
  is universally safe and that blue subject details can visually shift toward
  green/teal under despill. Task 30 records the approved future direction:
  retain the three visible manual colour buttons, add `Авто`, and persist the
  selected/observed key separately for each image
  through task recovery, Results, run report and diagnostics. Auto must choose
  before generation, reuse the same stored key for removal, validate the actual
  border and never trigger an automatic paid regeneration. A current-source
  adversarial test rejected orange `#FF6600`: the current single-dominant-channel
  algorithm removed a pure-red subject detail. No fourth preset was added and
  Chroma source remains unchanged.

Tasks 29–31 remain next-version work and require approved full screen/state
mockups before implementation. No release version, installer or provider
runtime is changed by this checkpoint. The current UI offers upscale only
before removal; Local Real-ESRGAN remains the future safe implementation for
the hidden after-removal stage, and Fal.ai ESRGAN is not treated as alpha-safe.

Verification is green after review follow-up: the focused Clipart/Processing/
provider/Chroma/state suite passes 178 tests and 28 subtests; the full offline
suite passes 1056 tests and 146 subtests, with 57 documented skips and two
intentional deselections. All tracked Python files compile, the tracked
sensitive-artifact scan and `git diff --check` pass. Fresh automatic Chroma
benchmark remains unchanged at alpha IoU `0.968704`, alpha MAE `0.018194`,
median 2048×2048 runtime `1.443 s` and peak RSS `421.203 MiB` below the
`448 MiB` ceiling. Independent review found two provider-cost cache/route edge
cases; both were reproduced by failing tests, fixed and accepted on re-review
with no remaining important or blocking findings.

Task 31 records the approved future provider/model availability check. It must
show separate KIE/Fal route states per paid stage, distinguish unavailable from
unknown and never create a paid task for preflight. A KIE terminal 422 after a
task was accepted is not sufficient evidence that the model route is globally
unavailable; likewise, Fal routes must not be shown as confirmed until the
corrected lifecycle contract passes the remaining controlled Windows smoke.

## Latest project checkpoint

Technical review fixes, the prebuild source-acceptance follow-up and the
Windows-native test handoff are integrated into `develop/3.1` by fast-forward
through `f90f04a`. Reproducible
tests confirmed and fixed paid-task persistence/recovery, cross-process journals, run/output
isolation and no-clobber publication, interrupted PNG/mask recovery, one
enclosed near-key Chroma data-loss path, the 40 MP editor boundary, QThread
signal lifecycle, Processing transparency action and release-safety defects.
The established workspace remains unchanged for the user: selected root
contains `rough/` and `output/`; a saved literal `output` path resolves
automatically to its parent, with no migration page.

The first release-candidate tree passed 1030 offline tests, 57 documented
skips, 2 configured network deselections and 140 subtests. Windows run
`33323248601` confirmed the native security contracts and exposed an incomplete
Real-ESRGAN v0.2.0 archive. Replacement run `33323775508` from commit `8c8c51c`
used the complete pinned v0.2.5.0 archive and passed every automated Windows
gate, including installed startup/UI and local processing. Its unpublished
`windows-3.1.0` artifact contains a `231576596` byte installer with SHA-256
`421aae337715057bbd44a808c0078d08689c04443225b2b1b1a19269a85b7f80`.

Subsequent Windows acceptance found the provider, diagnostics, rough-stage,
300 DPI and UI issues recorded above. The final follow-up tree passes 1056
offline tests and 146 subtests, with no important or blocking source-review
findings. The owner has authorized integration and a replacement Windows 3.1.1
build; publication and paid provider requests remain outside this build step.

Replacement Windows run `33350465599` from integrated commit `dee4fac` passed
all automated gates in 9m40s: native DPAPI and installer-lock contracts,
PyInstaller version/startup, signed Visual C++ prerequisite, Inno Setup,
installed UI/startup and Local Real-ESRGAN smoke, checksum, provenance and
release contract. Artifact `windows-3.1.1` (ID `9743579624`) contains
`VibixImages-Setup-3.1.1.exe` (`231576030` bytes), SHA-256
`1c89a48d4050322e5e5e62dcb881636784070c4cb68ce102029495b1b1c02946`.
The downloaded installer, sidecar and provenance match; a local server copy is
retained under `build-downloads/`. Repository visibility was restored to
private immediately after completion. No release was published.

The Windows observation pass subsequently confirmed a current-source Chroma
colour regression: fully opaque light-blue subject detail could be reconstructed
as green/teal. A synthetic adversarial test failed before the fix. Chroma now
preserves source RGB in the fully opaque subject interior while retaining edge
despill and all existing benchmark gates; the approved 3.2 per-item Auto key
selection remains deferred.

A later Windows diagnostic archive captured KIE succeeding with an RGBA PNG,
followed by Local Chroma failing the item because the border no longer matched
blue. The worker now defaults to preserving usable provider alpha even if a
caller omits the flow flag, emits the existing explicit alpha-reuse progress
message and completes the item without calling a remover. An RGBA channel alone
is not treated as proof: at least one transparent pixel is still required.

The Windows acceptance checklist now includes a clean-workspace duplicate
audit prompted by the owner's earlier candidate observation: one KIE prompt,
one requested variant and one provider task must produce exactly one ready
output. Current source tests and a direct claim check show that one journaled
KIE Task ID cannot be claimed twice within a worker; the old candidate did not
yet persist KIE IDs, so its visually identical files cannot be attributed to
task recovery without the original filenames/log. Windows evidence must retain
output names, SHA-256 hashes and the diagnostic journal if the symptom recurs.

The prebuild source-acceptance audit was completed on
`codex/chore-3.1-prebuild-acceptance` and integrated into `develop/3.1` at
`7addeee`. Tasks 2–6 were checked against current code,
tests and rendered UI rather than their stale checkboxes. The audit confirmed
Tasks 2, 3 and 6 in source and found two real UI contract gaps: the approved
Task 5 clean-background helper had never been connected and its color control
was still a combo instead of three visible buttons; the Task 4 Gemini action
used a longer unapproved label. Regression tests reproduced both gaps before
the fixes. The helper, three buttons, compact material wrapping and exact
`Удалить водяной знак Gemini` copy are now integrated.
Implemented screenshots for Tasks 2, 3 and 5 are stored beside their approved
mockups. The owner set the supported acceptance target to 1120×780 at Windows
scaling 100%; at that size Task 5 has no horizontal overflow. Linux offscreen
still measures `140 px` overflow at 980×700, but smaller windows and scaling
above 100% are accepted best-effort behavior and no longer block merge/release.
Remote Desktop is unsupported and outside acceptance. The focused
Clipart/Pinterest/Processing/output gate passes 215 tests,
55 intentional deferred Pinterest skips and 32 subtests; the unavailable local
Windows Real-ESRGAN binary accounts for one additional environment skip. The
complete offline suite passes 1026 tests, 55 skips, 2 network deselections and
140 subtests. All tracked Python files compile, the sensitive-artifact scan and
`git diff --check` pass. The fresh automatic Chroma benchmark remains within
its gates: alpha IoU `0.968704`, alpha MAE `0.018194`, 2048×2048 median
`1.357 s`, peak RSS `421.465 MiB` below the `448 MiB` ceiling.

Task 7 zoom presets are integrated in `develop/3.1` at `35931e3`:
редактор прозрачности предлагает `Fit`, `50%`, `100%`, `150%`, `200%` и
`300%`; прежний `400%` удалён. Выбранный масштаб сохраняется при переключении
между файлами. Focused editor/queue/processing suite (92 tests), `py_compile`,
`git diff --check` и sensitive scan прошли. Ручная Windows-проверка мышью
остаётся; стилус проверяется только на целевом устройстве, где он используется.

Task 6 output naming is integrated in `develop/3.1` at `6551011`:
готовые PNG остаются в `output/`, а промежуточные этапы — в `rough/`.
Генерируемый файл берёт короткое имя только из значения `Object`/`Объект`,
поэтому служебные слова `object` и `scene` больше не попадают в имя:
`Object: fox. Scene: …` даёт `fox_01_ready.png`; частые русские названия
переводятся в английские (`лисенок` → `fox`). Collision-safe suffix и
`_ready` сохранены. Focused output suite (35 tests), `py_compile`,
`git diff --check` и sensitive scan прошли. Владелец подтвердил сохранение
прежнего выбора рабочей папки без миграционной страницы: `rough/` и `output/`
остаются внутри выбранного root, а старый literal `output` автоматически
нормализуется в parent. Остаётся ручная Windows-проверка путей и реальных имён
на пользовательских промптах.

Task 25 is integrated in `develop/3.1` at `bdf6823`:
Fal.ai price refresh на Review & Run необязателен; подтверждающая галочка
удалена, а устаревший флаг подтверждения больше не передаётся worker. Кнопка
обновления цены расположена рядом со стоимостью и видна только при Fal.ai.
Успешная preflight-проверка не показывает техническую строку о ключе. Focused
suite (165 tests, 54 deferred skips), `py_compile`, `git diff --check` и
sensitive scan прошли.

Task 24 is integrated in `develop/3.1` at `aaf6a4f`:
Clipart и Pinterest ведут отдельные профили text/reference generation. Если
есть референсы, для их модели появляются отдельные списки модели, пропорции и
разрешения; несовместимые значения не предлагаются. Worker, runtime-проверка,
расчёт стоимости и Fal.ai quantity estimate выбирают профиль по каждой строке
промпта. Количество вариантов остаётся общим. Focused active suite
(185 tests, 54 deferred skips), `py_compile`, `git diff --check` и sensitive
scan прошли. Windows visual acceptance по-прежнему ожидается.

Task 23 is integrated in `develop/3.1` at `ea08918`:
режим обработки файлов после Results открывает тот же утверждённый редактор
прозрачности, что и Clipart. В список попадают только успешные PNG текущего
запуска; выбранный файл открывается сразу, а «Назад» возвращает к Results.
Отдельного нового дизайна нет: используются кисть, pan пробелом, масштаб и
экспорт существующего редактора. Focused offscreen suite для очереди и режима
обработки (75 tests), `py_compile`, `git diff --check` и sensitive scan прошли.
Windows visual acceptance по-прежнему ожидается.

Task 22 is integrated in `develop/3.1` at `f00cec4`:
Pinterest готовые промпты больше не показывают Chroma Key-helper; Pinterest
получает отдельный plain selector модели с референсом только для batch с
референсами. Task 24 позднее разделил также proportion/resolution, оставив
общим только количество вариантов; технические пояснения скрыты. Наглядный
ratio preview добавлен в общий Clipart generation page и поэтому доступен
также Pinterest. Approved mockups находятся в
`docs/ui/3.1/task-22-pinterest-prompt-no-chroma/`. Active prompt-only и
focused Clipart/Pinterest tests прошли; Windows visual acceptance по-прежнему
не выполнялась.

## Operating model

- VDS is the primary development environment.
- Windows is the environment for Windows-specific behavior and visual verification.
- GitHub is the source-code handoff point between environments. The last
  Windows 3.0.5 installer was built by the manual GitHub Actions workflow;
  the future 3.1.0 candidate also requires a separate explicit command. Azure
  remains historical/fallback infrastructure and is not queued here.
- Only one side edits the active branch at a time.
- Before changing sides, the active side runs relevant checks, commits, and pushes.
- The receiving side uses `git fetch` and `git pull --ff-only`.
- Windows-only tasks do not block independent Linux-safe work.
- Release pipelines are manual. Start a build only after a separate,
  explicit owner request and only for the platform named in that request;
  ordinary fixes, commits, and pushes must not start Windows or macOS builds.

## Current branch and handoff

- Target 3.1 integration line: `develop/3.1`; release-candidate and Windows
  acceptance follow-up branches are integrated locally for the 3.1.1 build.
  The retained source branches are not deleted.
- Windows-native acceptance follow-up `codex/fix-3.1-windows-native-tests` is
  integrated. It added real DPAPI and installer-lock tests without production
  code changes.
- Active release preparation is the integrated `develop/3.1`. Version 3.1.1 is
  set only for the explicitly authorized replacement build. The intended
  manual GitHub artifact is `windows-3.1.1`; Azure remains fallback
  infrastructure.
- Release baseline branch: `develop/3.0`
- Frozen 3.0.7 source line: `codex/fix-pinterest-prompt-only` at `78f8c63`.
  Its relevant history is already incorporated into the 3.1 ancestry; it is a
  historical reference and must not be integrated into `develop/3.1` again.
- The older `codex/docs-3.1.0-feedback-prd` branch is historical planning input,
  not the current handoff or implementation base.
- The older `codex/fix-windows-acceptance-ux-3.0.5` branch is not an
  implementation base: its 14 feedback commits diverged from current
  `develop/3.0`. Their product requirements are being consolidated manually
  into the separate 3.1 documents to avoid importing stale state or duplicate
  history.
- Ancestry audit confirms that the 3.0.7 source line already contains the
  recent Fal/localization, reference-preflight, generation-section and
  Pinterest-future-doc branches. `codex/tech-debt-11`,
  `codex/license-server-client-integration` and old CSV alternatives remain
  separate scopes and must not be merged into 3.0.7 or 3.1 merely because they
  exist.
- Provider-contract checkpoint branch: `fix/provider-api-contracts`
- Verified provider-aware source: `08648e2a623291b8ba90684e37d947b1db427a0f`
- Recommended VDS path: `~/projects/clipart-generator`
- Bootstrap: `bash scripts/bootstrap_vds.sh`
- Baseline: `python -m py_compile main.py` and `QT_QPA_PLATFORM=offscreen python -m unittest discover -s tests -v`

## Immediate next action

Download the preserved `windows-3.1.1` installer to the target Windows computer,
then perform the manual UI, mouse-editor, install/upgrade, path/output, license
and Chroma checks at
1120×780 and 100% display scaling. A stylus check is needed only when the target
device uses one. The one-prompt/one-variant KIE duplicate audit is a separately
authorized paid request. Publication remains a separate later decision.

The owner approved a post-3.1 product direction for the 3.2.0 mask editor.
Task 27 records visible zoom/brush shortcuts and a base «Умный контур» that
automatically draws a smooth closed curve through movable user nodes without
Bézier handles or image-edge snapping. The applied contour remains editable by
the existing brush and is one undoable mask operation. Optional magnetic edge
snapping with an on/off switch is a later stage so that hair, translucency and
low-contrast failures always have a predictable manual fallback. No 3.2 UI
mockup or implementation starts before 3.1.0 acceptance and a separate visual
approval.

## Historical implementation notes

Task 14 implements a seven-calendar-day offline grace only for a previously
verified license and only after timeout/transport/5xx unavailability. First
activation, explicit denial, a signed response already expired when received,
tampering, device/product mismatch, clock rollback and grace expiry remain
fail-closed. The approved and implemented UI screenshots are stored in
`docs/ui/3.1/task-14-license-grace/`. Focused license/update/release verification
passes 57 tests; the complete offline suite passes 950 tests, 56 intentional
skips, 2 deselected and 127 subtests. Compilation and tracked sensitive-artifact
scan pass.

Task 13 source integration is complete; the `3.1.0` candidate installer was
built successfully, but the first visual review found an approved Chroma helper
follow-up: blue stays the default for a new draft, selected materials use a
readable dark-turquoise state and selection is limited to three. The current
candidate is therefore not publishable. After this branch is integrated and
verified, create a replacement Windows candidate, then continue manual
acceptance for the image/mask editor, output/rough paths, chroma quality and
offline-license startup/run. Publication remains a separate owner decision.

Review checkpoint 2026-08-30: the remaining approved source fixes are now
integrated into `develop/3.1` through `554e944`: genuine-translucency prompt,
Processing transparency route regression, rendered-key edge recovery and
translucent colour correction. The merged tree passes 983 tests, 55 intentional
skips, 2 configured deselections and 133 subtests; focused tests, compilation,
diff integrity and sensitive-artifact scan pass. Automatic Chroma 2048×2048
uses `421.402 MiB` under the `448 MiB` ceiling. This checkpoint is ready for the
separate code review/refactoring task. No Windows build was started and
`release/VERSION.txt` intentionally remains `3.0.7` until release preparation.

The requested Fal.ai text-to-image catalogue expansion is integrated: Recraft
V4, Ideogram V4 Fast, FLUX.2 Klein 4B, Kling O3 Image and Bria Fibo Gen 1.5.
All remain text-only choices; attaching references keeps only models that
explicitly support them. Endpoint routing is registry-based so
`ideogram/v4/fast` and `bria/fibo-gen-1.5/text-to-image` correctly require
and use the Fal.ai key despite their IDs lacking `fal-ai/`. No live or paid
provider request was made.

Task 15 adds the approved compact «Что нового» block to the signed update
prompt and is integrated in `develop/3.1` at `ea57e12`. It does not add any
network request: it displays the existing manifest `notes` as plain text, hides
when empty, and keeps long text scrollable. Focused update tests and the full
offline suite pass (954 passed, 56 intentional skips, 2 deselected, 127
subtests).

Regression suite для накопленного 3.1 checkpoint синхронизирован с текущими
контрактами: prompt-only Pinterest, `output/rough`, имена `*_ready` и версия
3.0.7. Исправлена идемпотентность Pinterest draft round-trip; будущие six-slot
Pinterest-тесты сохранены как явно отложенные. Полный offline pytest проходит:
937 passed, 56 intentional skips, 2 deselected и 123 subtests.

Перейти к контролируемой оценке provider profiles после пополнения Fal.ai.
Preview, zoom, add/remove кисть, reset, атомарный экспорт и skip remover для
уже прозрачного PNG уже подключены. Ручная проверка приложения остаётся
финальным acceptance-шагом, а не частью платного тестового набора. Затем
подготовить эталонный набор изображений и после пополнения Fal.ai провести
контролируемое сравнение BiRefNet v2, BEN v2, Ideogram, Bria и rembg. До этого
зафиксировать endpoint `fal-ai/birefnet/v2` и режимы Matting/Portrait/Heavy.

Release 3.0.7 и development 3.1 разделены:

1. 3.0.7 остаётся immutable baseline `78f8c63`; новые пожелания туда не входят.
2. Перед публикацией отдельно проверить этот exact baseline, получить явное
   разрешение, fast-forward интегрировать его в `develop/3.0` и создать
   `release/3.0.7` от точного проверенного commit. Build/publish — отдельные
   явно разрешённые действия.
3. После freeze создать `develop/3.1` от точного опубликованного 3.0.7 commit и
   интегрировать туда утверждённые 3.1 docs.
4. Tasks 1–13 выполнять отдельными короткими ветками от `develop/3.1` и
   возвращать по одной с проверкой.

Локальный chroma-key для Clipart теперь добавлен как отдельная CPU-only
стратегия: prompt generator умеет добавлять инструкции для ровного ключевого
фона, а processing pipeline автоматически удаляет синий/красный/зелёный фон
без tolerance/softness, AI и сетевых расходов. Детальный путь сохраняет
отверстия, завитки, листья и иголки, сглаживает alpha внутрь контура и подавляет
цветной ореол. Для полупрозрачной кромки цвет берётся из самого глубокого
доступного чистого участка объекта на нескольких расстояниях, а подтверждённая
примесь ключевого цвета удаляется также из локальных непрозрачных пятен внутри
светлых деталей без изменения alpha. Детерминированные проверки включая JPEG
проходят; изолированный замер 2048×2048 использует 420,9 MiB при лимите 448 MiB.
Полный offline pytest: 939 passed,
56 intentional skips, 2 deselected и 123 subtests. Нужен финальный Windows UI
smoke на пользовательских сериях; Pinterest этим режимом не пользуется.
Материал `Прозрачные детали` получает усиленный prompt-контракт: сквозь тюль,
вуаль или стекло должны оставаться видны предмет либо тот же chroma-фон, а
непрозрачная pastel/key-coloured имитация запрещена. Контрольная генерация
подтвердила, что такой prompt действительно создаёт полупрозрачную сетку.
Comparison также выявил отдельный defect: candidate Vibix местами создавал
жёлто-зелёные участки внутри genuine translucent ткани, тогда как Clipbrook
сильнее удалял тонкую сетку. Prompt change не меняет remover; defect закрыт
отдельной targeted translucent-colour reconstruction без новых UI-controls.

Повторная проверка 2026-08-30 на восьми исходных owner PNG 2048×2048 выявила
и закрыла реальную причину жёлтой каймы: прежний staged de-spill искусственно
добавлял complementary channels после вычитания синего, а тестовый набор не
моделировал фактический rendered blue (`примерно #087CF3`). Follow-up branch
`codex/fix-3.1-chroma-quality` измеряет реальный border key, использует полный
multi-depth RGB reference предмета, восстанавливает key mixture без
противоположного оттенка и сохраняет первый различимый полупрозрачный ряд.
Blue/green/red regression, 43 focused tests и увеличенные black/white
comparisons проходят; изолированный 2048×2048 peak RSS `420.9 MiB` при ceiling
`448 MiB`. Full offline suite: 980 passed, 55 intentional skips, 3 deselected,
130 subtests. Дополнительный deselect — существующий stale Processing route
test, воспроизводимый без chroma change на чистом `develop/3.1`. User ZIP и
comparison outputs не добавляются в репозиторий.

Stacked follow-up `codex/fix-3.1-translucent-chroma-colour` закрывает жёлто-
оливковые островки внутри широкой полупрозрачной сетки. Коррекция ограничена
окрестностью подтверждённой полупрозрачной области и меняет только RGB:
alpha-маска, тонкие края и два остальных цветовых канала сохраняются. На
owner-approved юбке новый вариант оставляет больше непрерывной сетки, чем
Clipbrook, без прежнего жёлтого обрыва по нижнему правому краю. Blue/green/red
regression и полный offline suite проходят: 981 passed, 55 intentional skips,
3 deselected, 133 subtests. Automatic benchmark 2048×2048: `1.373 s`,
`421.402 MiB` при лимите `448 MiB`. Нужна Windows-проверка ещё на нескольких
реальных полупрозрачных материалах и разных preset-фонах.

Пресеты коррекции chroma-key не входят в текущую версию 3.1.0. В одной из
следующих версий после Windows-проверки и накопления повторяемых дефектов можно
отдельно оценить понятные варианты `Бережно` / `Обычно` / `Сильнее` и
контекстные действия для края или внутренних просветов. До этого основной
режим остаётся автоматическим и не показывает технические ползунки.

- обычная и reference-генерация используют отдельные selectors модели,
  пропорции и разрешения; существующие модели не удаляются, несовместимые
  варианты не предлагаются, а количество вариантов остаётся общим;
- общая настройка параллельности `35` отклонена: KIE, PhotoRoom и Fal.ai имеют
  независимый выбор 1/2/3 с default 3, а общий remote cap для всех трёх
  providers равен 6;
- Fal.ai key, connection и balance check уже подтверждены владельцем; Task 12
  добавляет утверждённый selector 1/2/3 и не переделывает balance flow;
- для каждого нового или существенно переделанного видимого раздела утверждён
  обязательный порядок: сначала полноэкранный mockup и состояния, затем явное
  `Макет утверждён`, только после этого source code. После реализации реальные
  screenshots сравниваются с макетом; PRD approval сам по себе UI не утверждает;
- chroma использует только pure blue/green/red без custom/HEX/eyedropper;
- Task 5 Chroma Key UI approved: compact helper справа, сначала короткие
  подсказки blue/red/green, затем пояснение про materials; material buttons
  остаются слева сразу после выбора цвета. Approved mockup:
  `docs/ui/3.1/task-5-chroma-advisor/approved-mockup.png`;
- Task 2 processing editor UI approved: compact operation checklist сверху;
  enabled stages ниже в pipeline order с тонкими разделителями. Approved
  mockup: `docs/ui/3.1/task-2-processing-editor/approved-mockup.png`;
- промежуточные файлы идут в `rough/`, готовые `_ready` — в `output/`;
- текущий встроенный Results mask editor не принят: требуется отдельная страница
  проверки, presets масштаба, видимый continuous brush и hardness;
- Local Chroma Key требует собственного автоматического prototype. Отдельный
  юридический gate не добавляется; при обычном code review проверяется только,
  что чужие файлы и фрагменты не переносились.
  Репозиторий Clipbrook скачан отдельно в
  `/root/projects/clipbrook-core-research` только для исследования поведения;
  его AGPL source уже был просмотрен как research reference. Изученные методы
  и идеи можно адаптировать, упрощать и улучшать, но code/constants/tests не
  переносятся. Работа не называется clean-room.

Не запускать платные запросы, Windows/macOS build, merge или публикацию до
соответствующего отдельного разрешения. Готовая исходная 3.0.7 публикуется
отдельно; текущая docs-ветка предназначена только для будущей 3.1.0.

## Pinterest Pins Task 6 checkpoint — 2026-08-28

- Feature branch `codex/feature-generation-fal-localization` implements
  selective one-slot regeneration and accepted-pin folder export; it is not
  merged into `develop/3.0` yet.
- Regeneration uses the original immutable `ProductLayer` when it is available,
  keeps its digest, and submits only the selected template or AI-scene slot to
  the existing Pinterest queue. No Fal client or live provider was added.
- Accepted successful variants export to the selected folder as JPG or PNG with
  collision-safe names such as `product_template_01.jpg` and
  `product_ai-scene_01.jpg`; a failed export preserves earlier files and shows
  the saved count and folder.

## Pinterest Pins Task 7 checkpoint — 2026-08-28

- The unmerged feature branch now declares an explicit Pinterest-only route:
  product photo, copy/layout, generation, six-slot preview, and export.
  Clipart prompt-review, cleanup and processing pages are no longer reachable
  in this workflow, and their operations are not allowed by its definition.
- New Pinterest visible strings, errors, statuses and accessibility names use
  the shared RU/EN message registry. Missing product, unavailable output folder,
  failed scene and partial export are covered for both locales.
- Provider capability rejection takes the no-network safe-template fallback;
  the source product remains protected. No Fal client, live API request, paid
  call or release build was added.
- Focused offscreen tests (68) and Python compilation pass locally; the branch
  remains unmerged into `develop/3.0`.

## Pinterest Pins Task 7 findings follow-up — 2026-08-28

- Follow-up commit `9c5e94d` removes legacy prompt/content-plan and processing
  fields from the canonical Pinterest state and route. Existing drafts retain
  those inputs only in the isolated `pinterest_legacy` migration archive, which
  is excluded from Pinterest requests and queue diagnostics.
- Product/folder and copy/layout now have distinct pages. The live Pinterest
  controller consumes capabilities, takes the safe local-template fallback when
  no AI-scene provider is installed, and shows the localized status.
- Focused workflow/state/Pinterest tests, compilation and `git diff --check`
  passed; no live provider call, paid request, build, merge or deployment ran.

## Replacement Windows 3.0.5 build — 2026-08-27

- All approved owner-acceptance source branches were integrated into
  `develop/3.0` and pushed as commit `02e03d0d666f58fe924c638ad994a8ba0700915a`.
- The combined source passes 738 tests, 1 expected Linux skip, 2 deselected and
  87 subtests; compilation, tracked sensitive-artifact scan and diff integrity
  pass.
- GitHub Actions run `33032049521` built only Windows 3.0.5, installed the
  resulting setup in a clean location, passed packaged startup, artwork,
  prompt-screen and release-contract checks, and uploaded the artifact.
- `VibixImages-Setup-3.0.5.exe` is 191,623,601 bytes. SHA-256:
  `5ab70b1df4eeab98f394b6a1bedde6f1915ae6a0d10325f8777b51327a4eda77`.
- macOS, Azure and update-service publication were not started.

## Generation settings clarity checkpoint — 2026-08-27

- Generation settings identify how many prompts have no references.
- Reference-model settings are hidden when the current prompt table has no
  references. When present, the section is clearly named and displays its
  prompt count.
- Clipart and Pinterest focused tests pass (67 tests). Full offscreen pytest
  passes: 733 tests, 1 expected Linux skip, 2 deselected and 87 subtests.
  Python compilation passes. No paid API request or build was started.

## Reference preflight and Review layout checkpoint — 2026-08-27

- New local references over 10 MB are rejected at selection time with file
  name, actual size and corrective action. Saved projects receive the same
  preflight before worker creation.
- HTTPS references are not silently downloaded merely to inspect their size;
  KIE responses for an oversized reference and official `402 Insufficient
  Credits` are converted to actionable user messages while bounded technical
  details remain available in diagnostics.
- The Clipart/Pinterest Review summary starts directly below its description,
  uses a common left edge and no longer distributes rows vertically.
- Focused Clipart/Pinterest/Results verification passes: 118 tests and 5
  subtests. Full offscreen pytest passes: 736 tests, 1 expected Linux skip,
  2 deselected and 87 subtests. Python compilation passes. No paid request or
  build was started.

## Provider-aware parallel stabilization checkpoint — 2026-08-26

- KIE and PhotoRoom now have independent 1/2/3 settings, each defaulting to
  3, behind a fixed six-task network cap. KIE's limit is shared by generation,
  Topaz, KIE background removal, and other existing KIE operations.
- Generation-only, processing-only and generate-then-process runs preserve
  per-image stage order while independent provider work can overlap. Local
  processing remains sequential.
- PhotoRoom uses its own launch guard: an initial burst of at most its selected
  provider limit, followed by a 60-images-per-minute pace. Bounded HTTP 429
  handling remains in force.
- Recraft payload, availability and no-silent-fallback behavior are unchanged;
  fal.ai remains excluded. Topaz remains limited to 2x/4x.
- Worker lifecycle events retain the exact item index. Results can show several
  active rows and route out-of-order output, failure and cancellation to the
  correct prompt/file. User-facing diagnostics exclude prompts, credentials,
  raw provider responses and full private paths.
- Focused offscreen regressions pass: 292 tests and 24 subtests. Full offline
  pytest passes: 724 tests, 1 expected Linux skip, 2 deselected and 87 subtests.
  Python compilation, tracked sensitive-artifact scan and `git diff --check`
  pass. No paid request, build, merge, push or server publication ran.

## Final concurrency audit — 2026-08-27

- Stop atomically closes admission at every paid provider POST boundary,
  including nested KIE work and PhotoRoom 429 retries. Already admitted tasks
  may settle; no new paid submission is admitted afterward.
- Mode switching and starts in another mode are blocked while any application
  controller owns an active run, preserving the application-wide remote cap.
- Structured cancellation closes every active/pending Results row; legacy
  aggregate progress no longer overwrites indexed progress, and retry
  diagnostics map back to the original item.
- Drive, UNC and POSIX paths with spaces share one redaction implementation in
  item errors, provider events and exported diagnostic archives.
- Full source verification: 731 passed, 1 expected Linux skip, 2 deselected,
  87 subtests; compile and diff checks passed. No paid call or build was made.
- The audited branch was fast-forwarded into `develop/3.0` and the exact merged
  commit `8aae4801718d1a33a427c886ded02a73fb284af6` passed the same full suite.
- GitHub Actions run `33026433664` built only Windows 3.0.5, installed the setup
  in a clean location, passed packaged startup/artwork and release-contract
  checks, and uploaded `VibixImages-Setup-3.0.5.exe` (191,609,853 bytes).
  SHA-256: `3e2efe15b4c35ab2163957715021297c3234e44ec613c989cc941f3e6242c7a7`.
  macOS, Azure and update-service publication were not started.

## Windows acceptance UX checkpoint — 2026-08-26

- Starting a mode, including the same mode from Results, now always opens a
  clean first step. Results exposes one same-mode restart action; mode switching
  remains in the shared header.
- CSV import has a primary top-of-page button, drag-and-drop, bounded mapping
  controls and a live three-row prompt/reference preview.
- Clipart and Pinterest can generate without processing. The Generation step
  no longer displays a partial estimate; Review separates images, generation
  calls, processing calls and their cost components from one calculation.
- Review no longer highlights API-key storage or a generic ready message.
  Processing Review also removes the duplicate external-transfer checkbox;
  choosing a network provider remains explicit on the preceding pipeline step,
  while missing-key and provider errors stay blocking and visible.
  Result hover previews close on pointer leave, app deactivation and Escape;
  terminal runs show a compact count/time/folder summary.
- Full offline pytest passes: 688 tests, 1 expected Linux skip, 2 deselected
  and 83 subtests. Syntax, sensitive-artifact and diff checks pass. No Windows
  build, paid API call or server publication was run for this checkpoint.

## Branded Windows installer checkpoint — 2026-08-26

- The installer source now uses Inno Setup's built-in high-DPI Polar dark style
  with the approved `#101827` surface and coordinated installer artwork.
- The visible flow is grouped into three stages: welcome, installation and
  completion. Destination and desktop-shortcut choices remain available while
  redundant Start Menu and Ready pages are hidden.
- GitHub and Azure Windows workflows pin Inno Setup 6.7.1, the minimum project
  compiler version supporting the selected style and background directives.
- GitHub Actions run `33002277766` built Windows version `3.0.5` from merged
  commit `631219f1b2494857d82f07a380e2f6cf538a4f02`. The workflow installed the
  finished package and verified the approved mode artwork and both prompt
  screens from the installed executable. The installer is `191583836` bytes
  with SHA-256
  `fceb6abfb44c2feb93ce8f2e2142987dc551fa47b0ddf1d7667341b6f12e8fef`.
  macOS and server publication were not run; the visible installer wizard still
  requires owner review on the target Windows computer.

## Provider contract checkpoint — 2026-08-26

- Ordinary generation no longer creates paid KIE availability probes; live
  model checks remain explicit user actions only.
- GPT Image 2, Qwen Image 2 and FLUX.2 use mode-specific documented ratios,
  resolutions, prompt limits, and reference limits before upload.
- Recraft Crisp, Recraft Remove Background and PhotoRoom preflight now match
  their documented file and image constraints.
- The deployed license service is recorded accurately: service URL approved,
  license and update terms implemented, and the admin panel uses username and
  password with TOTP as an additional second factor.
- Full offline pytest passes: 669 tests, 1 expected Linux skip, 2 deselected
  and 83 subtests; syntax, sensitive-artifact, startup-smoke and diff checks pass.
- No live/paid API request or release build is part of this checkpoint.

## Detailed diagnostics checkpoint — 2026-08-26

- Diagnostic schema v2 records a correlated timeline for each image: safe file
  metadata, stage/provider/model, parameters, duration, HTTP status, task ID,
  polling state, result count and bounded provider error.
- KIE generation/processing, PhotoRoom, RunPod and principal local processing
  stages emit structured events without additional network requests. Legacy
  progress parsing remains as a compatibility fallback.
- The journal can filter by severity, provider and image and displays Russian
  labels at the supported 980 x 700 minimum. Session storage remains bounded at
  8 MiB and 24 MiB total across the newest three launches.
- Exact prompts, API/licence keys, headers, full paths, URLs, raw responses and
  image contents are excluded from memory logs, persistent files and ZIP
  exports. Provider messages that echo the current prompt are redacted.
- `docs/API_CONTRACTS.md` records official links, current calls, diagnostic
  events and confirmed discrepancies; diagnostics does not claim those
  discrepancies are fixed.
- Full offline pytest passes: 653 tests, 1 expected Linux skip, 2 deselected and
  83 subtests. No live/paid API request, build or release was run.

## KIE Topaz checkpoint — 2026-08-26

- Root cause confirmed without a paid call: the application still sent the
  retired `topaz/upscale` model and silently replaced configured 4× with 8×.
- The worker, V3 state, provider registry and legacy config now migrate to
  `topaz/image-upscale`; the shared editor exposes only 2× and 4×, while old
  saved 1× values migrate safely to 2×.
- Local inputs are rejected before upload when they are not JPEG/PNG/WEBP,
  exceed 10 MB or would exceed 20,000 px on the longest output side. The error
  states that no KIE task was created.
- Full local pytest passes: 634 tests, 1 expected Linux skip, 2 deselected and
  83 subtests. No network or paid KIE request was made.

## Prompt flow checkpoint — 2026-08-25

- Clipart and Pinterest now use two explicit steps: prompt source/input, then
  series and reference review. The approved mode-selection screen is unchanged.
- The input step presents three visible source choices: generated series, one
  ready multiline prompt with up to five references, and CSV import. Sources
  only add; replace-all actions and the duplicate first-step table are removed.
- The generator combines objects × variations and joins only visible,
  user-entered fields. It adds no hidden mode text, numbering or requirements;
  the first two exact results and total count are shown before creation.
- CSV mapping has one import action, a brief count/error summary and automatic
  navigation to review; there is no duplicate preview table.
- The review step gives the prompt text two thirds of a larger table, supports
  search across hundreds of rows, and keeps compact prompt/reference actions.
- At that historical checkpoint offscreen screenshots were reviewed at
  1400×900 and 980×700. The current product decision supersedes 980×700 as a
  supported acceptance minimum; the variable text fields remain aligned and
  the 200-row review table uses internal scrolling.
- The whole V3 application starts at 1120×780 and technically can shrink to
  980×700 for best-effort use,
  preserves a user-resized window across menu and every route step, and gives
  large pages internal vertical/horizontal scrolling instead of resizing the
  top-level window.
- Full local pytest passes: 629 tests, 1 expected Linux skip, 2 deselected and
  78 subtests. No paid request or release build was started.
- GitHub and Azure Windows pipelines are configured to capture both prompt
  steps in addition to mode selection from the installed copy. Execution of
  the updated gate awaits a separately approved installer build.

## Current implementation checkpoint — 2026-08-24

The current product priority is to finish the existing interface and close the
remaining UX findings before adding new product modes. The immediate plan is
recorded in `TASKS_3.0.ru.md`: complete `CG3-TASK-034` (rendered UI smoke and
the remaining Windows smoke findings), then implement `CG3-TASK-035`
(controlled parallel KIE generation, initially up to three tasks with one new
task per second). Vectorization and Patterns remain deferred.

- Files and Results UX changes from `CG3-TASK-034` are implemented and covered
  by offscreen tests: file metadata is name/pixels/DPI/MB, overwrite is one
  safe-by-default checkbox, the drop zone is visible, Results uses a larger
  queue with hover/click preview, human duration, and one Diagnostics dialog.
- Local Real-ESRGAN subprocesses request hidden Windows console creation; the
  source registry still exposes both local background-removal providers
  (`rembg` and `BEN2`) and Local Real-ESRGAN for upscale.
- `CG3-TASK-035` has a first implementation: generation-only work uses at most
  three workers, launches new KIE tasks at no more than one per second, retries
  HTTP 429 with bounded backoff, and preserves per-item output/error handling.
- The release branch now also contains the previously divergent Files/Results
  UX work and controlled parallel-generation implementation. The packaged
  smoke can save 1366×900 screenshots of mode selection and Clipart prompts;
  GitHub produces them from the application after Inno Setup installation and
  uploads them beside the installer for visual review.
- Full local pytest passes: 613 tests, 1 expected Linux skip, 2 deselected and
  73 subtests. No paid KIE request was made. Windows installed-copy rendered
  smoke and a small real KIE speed/credit run remain pending.
- GitHub Windows run `32906900417` succeeded from source commit `9222eea`.
  Inno Setup installed the application into a clean directory; the installed
  executable passed version, startup, artwork and native-Windows rendered UI
  checks. The downloaded installer is `191310485` bytes with SHA-256
  `1a93d54e4c555ef6a0f70523b0ff9126ff7b636dd148c75b9c3a80aaf5b7fd7f`.
  Its two readable screenshots confirm the three approved raster illustrations
  and the current Clipart prompt workspace. Server publication was not run.

The Windows 3.0.1 smoke test covered installation, startup licensing, folder
persistence, diagnostics, local processing, cancellation, and basic lifecycle.
Unchecked acceptance items are `SKIP / NOT TESTED`, not proven passes. Do not
upload or publish an update revision until the current source and focused
acceptance are approved.

## Blockers and risks

- Azure Windows run `141` was requested from the merged `develop/3.0` commit
  `5732eedd` on 2026-08-26 but Azure rejected the job before checkout because
  the organization had no free hosted minutes. GitHub Actions run
  `32977293110` replaced it, built Windows only from the exact same commit,
  installed the finished package, and passed the installed-copy artwork and UI
  evidence gates. The downloaded `VibixImages-Setup-3.0.5.exe` is `191362608`
  bytes with SHA-256
  `6c3f4837b381f2da44cd0d54fa4b8fce8ec03b047227efc9e3b57c226d8daba6`.
- The deployed license service and signed desktop contract are active. VDS,
  DNS, TLS and PostgreSQL availability is a direct dependency for first
  activation, explicit server decisions and continued work after the bounded
  seven-calendar-day grace expires; a qualifying temporary outage does not
  immediately block a previously verified license within that grace.
- The local legacy `licenses.db` is ignored and no longer tracked in source
  control; server-side license state must use the configured external database.
- Automated packaged checks passed, but final installation, production-license
  activation, Windows visual behavior, and SmartScreen behavior still require a
  manual check on the target Windows computer.
- Owner testing of the superseded GitHub `3.0.5` showed the pre-artwork card
  layout even though the downloaded installer hash matched run `32900235313`.
  The old gate checked only that three cards existed. The replacement source
  now rejects null card pixmaps and verifies the application again after Inno
  Setup installs it.
- The same owner test exposed visible helper-process console windows. Root cause:
  the `CREATE_NO_WINDOW` change existed only in divergent commit `82fe6ff` and
  was absent from the artwork release branch. The focused fix is now applied to
  Local Real-ESRGAN and all optional local watermark subprocesses. That
  superseded artifact is not a publication candidate; replacement run
  `32977293110` contains the fixes and awaits owner target testing.
- VDS access to the private GitHub repository and Codex authentication must be configured outside Git; no credentials are stored here.
- Linux cannot replace Windows visual and packaged-client verification.
- Azure Windows run `81` proved KIE balance and KIE processing on the owner's
  Windows machine, but its bundled Real-ESRGAN runtime is incomplete and Local
  rembg packaging was not covered by the packaged smoke gate. Source fixes are
  verified locally; a new Windows build remains `WINDOWS_REQUIRED` and may run
  only after explicit owner approval.
- Do not start an Azure Windows or macOS release build unless the owner
  explicitly requests that platform's build after the desired fixes are ready.
- Source now keeps successful worker completion on Results and records an
  ordered privacy-safe technical trail. The exact packaged Windows focus,
  layout, and exported-ZIP behavior still require the next approved build.
- The verified 3.0.1 installer and Azure run `77` artifact are historical
  evidence only; neither contains the current fix pack.
- The current source candidate passes 557 unittest tests and 584 pytest tests
  plus 73 subtests. The expected Linux skip remains because the Windows
  Real-ESRGAN binary is unavailable there. Windows/macOS packaging and manual
  target-machine acceptance remain the final platform-specific checks.
- Final Azure Windows run `102` and macOS run `103` both succeeded from commit
  `a085167e0e311856a4cacedf0c85a6b7147bdc47`. The downloaded Windows installer
  is `204556261` bytes with SHA-256
  `66b011747948f57065ce5a2b3004a74e3a7df55702694f08060d18d195f49db7`.
  The downloaded macOS ZIP is `245668325` bytes with SHA-256
  `ba8d0cc134f0ad8b75dfd419889d942cf5e202ef4db307320a8a771c4b3c6887`;
  its sidecar matches and `unzip -t` reports no errors.
- Windows target testing invalidated run `102` for publication: Local rembg
  cannot initialize `onnxruntime_pybind11_state`, and Local BEN2 is absent from
  its release UI. The source repair now bundles the Microsoft Visual C++ x64
  prerequisite, removes stale native runtime files during upgrade, verifies an
  installed copy in Azure, restores BEN2 through the pinned official 223 MB
  ONNX model, and performs real rembg/BEN2 packaged inference. A replacement
  Windows build was replaced by verified run `116`.
- Final 3.0.3 Azure Windows run `116` and macOS run `117` both succeeded from
  commit `6ed15376d74753078aab6c82a7ae29b673e40fbe`. The downloaded Windows
  installer is `222630658` bytes with SHA-256
  `d9acd80fe1c87aa10e2294b5456ccb67709e6fa9effe9acefa3b023b552eadfd`.
  The downloaded macOS ZIP is `245716567` bytes with SHA-256
  `ae18022315b459b37906f2c0f8ced34b07f26bfb7af97eb2c0a9a6bd6e3b62f9`;
  both sidecars match and the macOS archive passes `unzip -t`.
- KIE documentation still lists `recraft/crisp-upscale`, but that does not
  prove account/region availability; the implementation does not silently
  switch a failed Recraft task to another paid model. Topaz remains the safe
  default.
- The Windows smoke test found a misleading offline saved-license key prompt,
  an enabled SynthID consent control for an unavailable capability, stale file
  UI after `process more`, a clipped/incorrect wizard header, and slow eager
  first-mode initialization. These are tracked in Task 65.
- Do not start Azure/GitHub Actions Windows packaging for the current version
  until all known source issues are resolved and the owner explicitly approves
  the final build run.
- The installer from run `31909510317` predates the new updater and diagnostic
  journal. Use the verified `3.0.1` installer from run `31924194111` for current
  acceptance.
- Secure update delivery is deployed and the Windows artifact exists, but no
  `3.0.1` revision is published yet. Manual Windows installation should precede
  a controlled draft upload and end-to-end update test.
- The macOS build is intentionally unsigned and not notarized. Gatekeeper will
  warn on first launch; the application must not automate bypassing that warning.
- The mode-selection screen now uses packaged 1774×887 PNG illustrations for
  the three primary workflows (clipart, Pinterest pins, and image processing),
  matching the public download page. Windows Inno Setup uses the coordinated
  `assets/installer-wizard-hq.png` artwork and retains the workflow/license
  messaging. Replacement GitHub run `32977293110` verified these assets from an
  installed copy; final visual acceptance remains pending on the owner's
  Windows computer.
- Azure's hosted macOS ARM64 preview is paused. The Azure artifact is x86_64 and
  requires Apple's free Rosetta 2 on Apple Silicon; a native ARM64 build would
  require a self-hosted Apple Silicon agent or a different CI provider.
- Azure run `91` succeeded from source commit `6b41682`; artifact `macos-x64`
  contains `VibixImages-macOS-3.0.2-x64.zip` (`245630259` bytes) with SHA-256
  `04d4bf58f085f5239a7a6a5c46c3b6470d32ee6d116828ee383d29708399f6d9`.

## Approved brand direction

- Product name: `Vibix Images`.
- Subtitle: `AI Image Generation & Processing`.
- Shared family mark: a solid white `V` plus one separate dark pixel at the
  lower right, aligned to the same lower baseline.
- The canonical geometry and portable SVG are recorded under `docs/brand/` and
  in `docs/superpowers/specs/2026-08-17-vibix-shared-mark-design.md`.
- Branding is integrated into the application runtime, Windows icon set, and
  Inno Setup configuration. The current Windows installer naming convention is
  `VibixImages-Setup-<version>.exe`; GitHub run `32977293110` is the current
  verified Windows 3.0.5 acceptance candidate.
- Previous license keys did not exist, so no license-key migration is required;
  the first Vibix Images installation activates a new key through the existing
  online license flow.

## Pinterest Prompt-Only MVP checkpoint — 2026-08-29

- Active Pinterest route now contains work folder, ready prompt or CSV,
  prompt/reference review, model/format, review/run, and shared results.
- Default Pinterest generation format is 2:3; the old product upload, six
  fixed templates, AI scenes and image-processing controls are no longer active.
- Pinterest reuses the shared Clipart generation request/queue and supports the
  existing KIE/Fal runtime gates without making live or paid requests.
- Focused offscreen checks pass: 104 tests plus 11 subtests, and the Pinterest
  mode suite passes: 24 tests plus 6 subtests. Manual desktop acceptance remains.

The alpha/transparency brush editor on the Clipart results page is temporarily
hidden for the stable client release, including corrected-PNG and alpha-mask
save buttons. The implementation remains available for the future dedicated
image-processing version.

## Prohibited without explicit approval

- Secrets, credentials, `.env` files, and user data in Git.
- Force push, destructive cleanup, automatic rebase, or deletion of uncertain branches/worktrees.
- Production workers, paid API operations, deployment, release/build publication, or account actions.
