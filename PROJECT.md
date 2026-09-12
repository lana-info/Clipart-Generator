# Vibix Images

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

Automatic set export UI is now summary-first. The main screen shows only unique
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
