# Project state

Updated: 2026-09-11

## Current handoff: automatic set export UI completed, 2026-09-11

Approved export redesign is implemented. Summary is primary; manual membership
editing is optional and isolated on its own matrix screen. Main UI shows unique PNG
count + dynamic set count, uses plain-language delivery wording and one stable
`Создать наборы` action. No confirmation checkbox or redundant Close button.
Hovering a filename in the manual matrix opens a bounded preview beside the mouse.
The return button is sized to its label.

Current-run bundle issues are derived from stable object IDs: zero successful
exportable PNG => missing, more than one => ambiguous. Either blocks export and
shows `Проверить сейчас`; no variant is silently selected. Existing manual
assignments/exclusions and unrelated historical memberships remain preserved.
Focused export/queue/contour regression: 82 passed + 5 subtests. Full isolated
pytest: 1383 passed, 57 skipped, 2 deselected, 232 subtests in 61.09s. Final
independent review: NO P1/P2 FINDINGS. Real Qt proofs are in
`docs/ui/3.2/auto-set-export-proposal/`. No build, paid calls, actions or deploy.

Independent read-only review of commit `3d48468` found three P2 export issues:
duplicate session records for one PNG were counted as ambiguous, unsaved matrix
changes affected export, and manual resolution could not clear an ambiguity block.
All three are fixed in `5688c1a`; the same-path duplicate seeding path was also
hardened. Review-fix verification: 21 focused passed; full isolated pytest 1387
passed, 57 skipped, 2 deselected, 232 subtests.

Automatic planner expansion is now ready for commit: schema v2 keeps nested
Mini/Standard/Maxi/Full Bundle and adds deterministic thematic sets from object
roles. A 30-image balanced collection proposes 6 useful sets; larger collections
can propose 7-8. Empty/exact-duplicate sets are rejected, stable IDs and user titles
survive replanning, and legacy schema v1 validates/migrates without changing
commercial set IDs. Combined targeted verification after `5688c1a`: 128 passed +
32 subtests. Final combined full isolated pytest: 1390 passed, 57 skipped,
2 deselected, 233 subtests in 60.61s. Local read-only diff review found no new
P1/P2. Per owner decision, external Codex CLI review is no longer a mandatory gate
when unavailable. No build, paid calls, workflow dispatch or deploy.


## Current handoff: many-to-many completed, 2026-09-11

Many-to-many export membership завершена. Legacy назначения мигрируют в version 2
со стабильными asset/set ID и точным backup перед первым overwrite. Один PNG
сохраняет несколько независимых memberships и может переиспользоваться в
нескольких ZIP без повторной генерации. Contour-copy переносит memberships.
Отдельно исправлена нормализация ошибки migration-backup в standalone draft.

Focused verification: 31 passed, 8 subtests. Full isolated pytest: 1369 passed,
57 skipped, 2 deselected, 228 subtests in 60.63s. py_compile and git diff --check
passed. Final independent read-only review: NO P1/P2 FINDINGS. No paid calls,
builds, deployments or workflow dispatches.

Automatic mini/standard/maxi/full-bundle planning is now implemented before
prompt handoff. The planner uses stable object IDs, role-aware deterministic
ranking, strictly nested tier prefixes and fewer tiers for small collections;
set IDs survive replanning and recipe roundtrip. No provider/API call is involved.
Focused: 32 passed + 4 subtests. Full isolated pytest: 1372 passed, 57 skipped,
2 deselected, 232 subtests in 64.40s. Independent final review: no P1/P2.

Saved Bundle Plan is now connected to successful current-run outputs. Compiled
Clipart prompts retain internal object_id through project persistence, prompt
editing/copy/batch/duplicate paths, run request, queue and retry. worker_kwargs
still sends only provider-required fields, so object_id is not exposed upstream.
Before set export, a unique successful PNG is seeded with every planned set
membership that contains its object ID. Existing manual membership is preserved;
multiple successful variants for one object are left unresolved for Review instead
of silently choosing a file. This adds no generation or processing request.

Initial independent review found two P2 metadata-loss paths in batch edit and
duplicate/copy flows; regression tests reproduced them and all were fixed. Final
focused verification: 204 passed, 27 subtests. Full isolated pytest: 1377 passed,
57 skipped, 2 deselected, 232 subtests in 60.50s. Final independent read-only
review: NO P1/P2 FINDINGS. No paid calls, builds, deployments or workflow dispatches.

Next task in order: make the automatic plan the normal export path and move the
manual assignment table behind an optional «Изменить состав наборов» action.
This is a user-visible flow change and therefore requires the AGENTS.md visual
approval gate before implementation.

## Preparation review fixes, completed verification 2026-09-11

Owner authorized preservation of the accumulated work on the current branch,
including correction of three independently reviewed P2 defects. This preparation
supersedes the documentation-only pause below, but does not start pending features.
Contour copies now update the current successful result and its export membership;
explicit editor copies outside the output folder are accepted without admitting
unrelated folder files. Originals remain unchanged. Export membership path keys
are validated by their schema, not treated as credential field names; actual
credential fields remain rejected. Bounded contour history advances its retained
base on eviction instead of jumping to the original alpha. The base consumes the
history byte budget; Reset still targets the immutable original.

All three defects reproduced before the fixes. Focused integration/queue/project/
history checks: 211 passed, 14 subtests. Full isolated pytest: 1361 passed,
57 skipped, 2 deselected, 223 subtests (62.48s). Mandatory unittest: 1252 tests,
57 skipped, exactly two socket PermissionErrors under the sandbox (56.94s).
The orchestrator reran exactly those two socket tests with require_escalated:
both OK, 2 tests in 0.204s, exit 0. This closes the sandbox failures without
claiming a fresh single full unittest run outside the sandbox. Compilation,
startup smoke, tracked artifact guard and diff-check passed.
New independent reviewer 01a08dc1-babe-7e62-afa5-f3c549b2f52a reported no justified
findings within the three fixes and integration scope; independently ran
93 tests and 8 subtests, including modal Qt, external/repeated contour copies,
ZIP/PDF, stale source rejection, membership paths/credential protection and
bounded Undo. Both verification and review gates are satisfied.
This is a reviewed preservation checkpoint, not a Studio release. No build,
paid API or deployment; all test processes completed. Owner authorized committing
the accumulated snapshot with [skip ci] and pushing this same branch without force.
Git records the preservation commit and remote synchronization; do not restart
completed tests absent new code changes. New product tasks remain unstarted.
Staging normalized trailing whitespace only on three lines of the imported
production-pipeline text and one line of the historical HTML mockup; no source
wording or runtime code changed in this final hygiene pass.
See docs/ERRORS.md for causes and regression coverage. Product priorities remain
TASKS_VIBIX_STUDIO_3.2.ru.md: many-to-many membership first; its implementation
is currently only an unfinished local working copy.

## Paused by owner after documenting latest decisions

Latest request supersedes earlier continue-until-finished instructions: record
decisions and stop. This turn changes documentation only; no code, paid calls,
build, commit or new runtime tests. Last implementation verification remains
1357 passed / 57 skipped / 2 deselected / 220 subtests, not a new test result.

Approved direction: minimal manual work across the workflow; user supplies brief,
reviews and corrects. Automatically plan mini/standard/maxi/full-bundle contents
before generation; default nested proposals, one asset in multiple sets (3–4+),
generate/process once and reuse exact PNG across separate ZIPs. Keep paid consent
and quality review. Manual distribution becomes optional "Change set contents".
Current export_membership is path -> one title/included; current UI is manual.
It DOES NOT implement many-to-many or automatic tier planning. Migration must
preserve existing assignments/exclusions and never trigger generation.

Expand current eight palettes to categorized 5–7-swatch cards with recommendations:
holidays/seasons/nature (sea, forest, mountains, sand, clay, flowers, berries, fruit),
color families (sage, lilac, blue, beige, pink etc.) and application. Optional
pastel/muted/saturated/contrast, custom and reference-derived palettes. Collection
and all subsets share the selected art direction; references also inform technique,
objects and mood. No expanded catalog has been implemented in this turn.

Hard UX constraint: no background-removal method/algorithm name or technical key
color anywhere user-facing, even settings/help/errors/progress/user diagnostics
or deliverables. Use outcome-only wording; retain internal engineering details
and checks without leaking them. This does not hide generation provider/model
selection or prices. User-surface audit and cleanup are still pending.

After the stopped working copy is resumed and completed, follow the latest
priority checklist in TASKS_VIBIX_STUDIO_3.2.ru.md: finish many-to-many, then
implement automatic plans, optional editor, palette expansion and UX audit.
Historical checkpoints below describe actual existing code, not completion of
these new requirements.

## Latest increment: result-to-ZIP UI connected

RunResultsPage now exposes Export sets ZIP for Clipart only. Disabled before/while
running or without usable successful outputs. Candidate selection uses only this
session's recorded successful PNG output paths within output_dir, excludes symlinks
and duplicates, and never scans the folder for older/unrelated PNGs.
SetExportDialog supports inclusion checkboxes, editable set membership and bulk
assignment to selected rows. Default membership is explicitly visible as Set 1;
users review/modify before export, not inferred from subject/completion order.
Manual review checkbox is reset when inclusion or membership changes.

Actual export runs in QThread, creates separate ZIPs through studio_set_export,
and reports the new destination folder. Cancellation is cooperative between
file/set/PDF steps and before publication; close waits for cleanup rather than
destroying an active worker. No partial publication if cancelled before commit.
If publication already completed, success is reported, not a false cancellation.
No source PNG bytes changed. Explicit Save membership stores path-keyed title and
inclusion through optional clipart.export_membership and shell.state_changed
autosave. Other-run assignments are preserved; legacy drafts omit the field.
Invalid membership is rejected before overwriting a valid draft. Reopening restores
membership but never restores the visual-review checkbox. Paths aren't portable
IDs: moving/renaming outputs still requires reassignment.
This is packaging UI plus explicit user review, NOT automated alpha-quality
certification or a complete image-review/editor workflow.

Focused checks: 69 passed, 5 subtests, including real threaded PDF/ZIP export,
two-set membership, review gate, cancellation cleanup, current-session-only paths
and exclusion from other modes. Initial fixture bug destroyed QApplication too
early; fixed fixture lifetime using yield, rerun succeeded. Real Qt export screen
inspected offscreen at 1120x780; final artifact:
docs/ui/3.2/export-sets-1120x780.png (dummy names, actual Qt screen).
Persistence-focused checks: 101 passed, 27 subtests. First full-suite checkpoint
before persistence: 1355 passed, 57 skipped, 2 deselected, 220 subtests (60.50s).
No paid calls/build/commit. Next: image-reference
handoff and integrated local alpha/QC acceptance; KIE tariff and live probes remain.
Final full suite after persistence: 1357 passed, 57 skipped, 2 deselected,
220 subtests (60.45s). git diff --check passed. Skips remain Windows-specific
contracts, unavailable RealESRGAN and deferred Pinterest. Windows/live API not tested.

## Latest increment: working planning controls and per-set export core

Owner requested continuing all stages autonomously; paid probes, release builds,
publishing and Windows acceptance still require separate authority/environment.
Continued existing feature branch; preserved accumulated changes; no commit/push.

OpenRouter credential now has a masked field in ApiSettingsDialog, runtime secret
handoff and SECRET_CONFIG_KEYS exclusion from normal config. Storage is the SAME
plaintext user .env as KIE (not encrypted); no secret is put in recipe/draft.
Composite credential save rejects multiline values before modifying stores;
UI save errors keep the dialog open with a sanitized message.
Recipe.assistant stores only validated provider/model and preserves old drafts.

PlanningPanel is connected to the actual builder page: provider-filtered models,
replace selected / propose all unpinned, background tariff fetch and generation,
explicit confirmation, discard-on-cancel, stale validation before paid launch and
before apply. Default is OpenRouter Gemini; GPT-5 mini and DeepSeek Vision selectable.
Current OpenRouter tariffs come from GET /api/v1/models (no generation). UI estimate
uses input byte count + overhead and 16000 output tokens; explicitly not a dollar
cap or tokenizer measurement, excludes platform fee. provider.max_price enforces
confirmed token/request tariffs, not aggregate spending. No auto retry/fallback.
KIE can be selected/saved but launch is blocked pending verified tariff/cost controls.
Cancellation does not refund/abort an already submitted upstream request; results
are discarded. Worker connection/read timeouts still aren't a total deadline.
References still only supply manual text observations; no image transmission.
Real Qt screen checked offscreen at 1120x780: /tmp/vibix-planning-ui.png (temporary).

studio_set_export.export_clipart_sets accepts explicit final-PNG membership per set
and publishes a new folder with one ZIP per set: PNGs, Letter overview.pdf and a
minimal manifest with hashes/dimensions. Snapshots preserve source PNG bytes.
All archives stage before publication; failure leaves no partial output folder.
This export API is tested but NOT wired into result review UI; no set membership
is inferred from completion order or filenames. Alpha quality is caller-reviewed,
not certified by the archive function. Limits: 100 sets, 1000 PNG/set, 64MB/PNG.

Next: reference-image analysis consent/handoff, live provider acceptance with a
separately approved text budget, integrated alpha/QC review and explicit set
membership → export UI. Patterns/Junk Journal/release remain incomplete; do not
call the overall project finished. Full isolated suite: 1349 passed, 57 skipped,
2 deselected, 220 subtests (61.24s). Skips remain native Windows contracts,
unavailable RealESRGAN and deferred Pinterest. No paid API checks or build.
Focused UI/settings check: 42 passed; export/planner/client: 18 passed with
11 subtests before the final full run. git diff --check passed.

## Latest increment: selected text models and single-request adapter

Owner approved KIE and OpenRouter, Gemini 3.8 Flash, DeepSeek V4 Flash Vision Exp
and GPT-5 mini (not 5.4 mini). PROJECT/PRD/tasks reflect confirmed exact routes.
studio_text_models.py permits Gemini through KIE and all three through OpenRouter.
studio_text_client.generate_plan takes explicit runtime credentials/approval,
snapshots recipe, sends one request and returns validated proposals without
mutating draft. No retries, redirects, model fallback, tool execution or uploads.
OpenRouter uses strict JSON schema; KIE relies on local validation and accepts
chat/native Gemini envelopes due to inconsistent published docs. No unsupported
KIE token/schema parameters guessed. Therefore no KIE monetary/token cap claimed.
80-target/200KB brief/2MB response limits, connect/read timeout, sanitized network
errors. Timeout is not a total wall-clock deadline; cancellation remains pending.
Only manual reference observations are sent, not images. The runtime approval
boolean is a launch gate, NOT a budget cap or complete UI consent implementation.

Next: OpenRouter secret storage + provider/model settings, cost preflight and
asynchronous builder integration; inspect live responses only with paid-test
authorization. No key read, paid call, dependency, build, commit or UI change.
Focused verification: 14 passed and 11 subtests with mocked HTTP, including pins,
invalid IDs, no fallback, explicit approval, redirects, oversized and bad replies.
Full isolated suite: 1334 passed, 57 skipped, 2 deselected, 220 subtests (60.36s).
Skips remain Windows contracts, unavailable RealESRGAN and deferred Pinterest.
git diff --check passed. Live provider compatibility and Windows UI not tested.

## Latest increment: safe automatic-planning boundary

Owner approved automatic ideas from the brief as the primary path, with optional
manual editing. PRD/PROJECT/tasks updated. studio_clipart_planner.py assembles
brief/palette/manual reference observations and selected unpinned targets; accepts
complete validated suggestions atomically without changing IDs, ordinals or roles.
Stale responses are rejected by matching the request against the current draft.
Local reference paths are excluded. This is offline data logic, not a live AI
client; no semantic image analysis or network request has been implemented.
Optional pinned bool is backward compatible and persists in recipes. ObjectEditor
has a pin checkbox; page renamed Proposed Set, but manual editing is still the
only connected workflow until the text adapter/planning actions are implemented.
Next: verify an existing-provider text API/model and cost, implement asynchronous
adapter with explicit budget/preflight, then wire initial/single/unpinned proposals.
No new provider, dependency, secret access, paid request, build or commit.
Official API discovery: https://docs.kie.ai/market/gemini/gemini-2-5-flash
documents an existing-provider chat-completions endpoint and structured output.
This is an adapter candidate, not a final model choice or a verified price.
Next session need not search for a new provider first. Focused tests: 16 passed;
offscreen ObjectEditor pin interaction and screenshot checked (not full Windows
visual acceptance). Full isolated suite: 1326 passed, 57 skipped, 2 deselected,
209 subtests passed (59.75s). Skips remain Windows contracts, missing RealESRGAN
and deferred Pinterest workflows. git diff --check passed.

## Latest increment: concrete objects and explicit prompt handoff

Builder now includes an ObjectEditor after recipe structure (five local pages).
Objects have stable IDs/ordinals, role, name, action/pose, extras, layout/shape
and details; add/duplicate/remove/edit persist through optional recipe.objects.
Recipe expansion adds blank slots, never invents named AI objects or deletes
edited rows. Returning from objects synchronizes role totals so Back/Next does
not resurrect deleted entries. Incomplete objects may be saved as drafts.

An explicit unchecked option appends prompts on Save using the existing
generate_prompt_series language/chroma pipeline. Empty names or count mismatch
block handoff atomically; existing prompts remain. Existing chroma enablement
is respected; it is not yet a fully automatic module processing profile.
Reference images/notes are not attached to new prompts in this increment.
AI object suggestions, reference handoff, final integrated launch/review/export
and per-set ZIP remain pending. Real populated Qt screen inspected at 1120×780.
Verification: full isolated suite 1320 passed, 57 skipped, 2 deselected,
209 subtests (59.25s). Tests cover object draft roundtrip, append without
overwriting, invalid handoff atomicity, stable IDs and Back/Next deletion.
git diff --check passed. No paid calls/build; native Windows still unverified.

## Latest increment: separate reference screen and local palette

The builder now has four working pages: idea, visual settings, references,
recipe structure. ReferenceEditor stores up to 20 PNG/JPEG/WebP references with
multiple roles (technique, palette, mood, subject, character, pose, composition)
and editable manual observations. Optional recipe.references round-trips through
the existing validated draft; missing files do not prevent reopening the project.
Files stay at their original paths (portable copying is still pending).

Local palette extraction uses a bounded EXIF-oriented thumbnail and ignores
transparent padding; explicit apply updates the editable palette. No upload or
AI interpretation occurs. Source files remain unchanged when removing entries.
Source mapping: 2026-06-05_130634.png -> presets/custom/from-image palette;
Characters/Holiday/Junk Journal review -> distinct visual/subject/mood roles.
Crop/region selection, automatic semantic analysis, object planning and final
prompt/reference handoff remain pending. A full eight-step app is not claimed.
Qt reference screen inspected at 1120×780 offscreen; Windows not tested.
Verification: 1314 passed, 57 skipped, 2 deselected, 209 subtests in the full
isolated suite (62.71s). Reference/recipe/draft focused checks passed; source
preservation, transparent-padding palette, role roundtrip, cancellation and
missing-file reopening covered. git diff --check passed. Empty and populated
real Qt screens inspected locally. No paid calls, new dependencies or build.

## Latest UI increment: editable set settings

Owner explicitly authorized implementing the described screens without another
mockup approval loop. ClipartProjectPage now opens ClipartBuilderDialog using
the existing theme. This first working block includes idea/custom context/motifs,
visual settings, eight palette cards, and recipe distribution. Back/Next and
explicit save work; Cancel preserves all project state. Visual selections are
stored separately in optional recipe.visual and compiled into the existing
prompt_generator.style; palette uses the existing field. Existing prompts are
not overwritten. Pinterest has no builder entry.

This is not yet the complete eight-screen workflow: separate reference editing,
concrete object planning, full prompt/queue integration and per-set ZIP remain.
The dialog has three local pages until the remaining workflow is integrated.
Real Qt style screen inspected at 1120×780 offscreen; Windows acceptance remains.
Verification: full suite 1309 passed, 57 skipped, 2 deselected, 209 subtests
(59.73s); after restricting the entry to Clipart, four builder tests passed,
including Pinterest exclusion. git diff --check passed. No paid calls/build.

## Latest implementation: offline Clipart recipe persistence

studio_clipart_recipe.py allocates the exact requested total across five roles
using three weighted recipes. Explicit manual edits update the total and retain
zero categories. Theme/custom context/related motifs and counts persist through
optional clipart.recipe in the existing V3 draft. Legacy drafts omit the field;
invalid or future recipe schemas fail before overwriting a valid draft.
No provider call occurs during planning or loading. This increment implements
the data layer only; builder screens, reference extraction, object-to-prompt
handoff and multiple-set ZIP integration remain open.

Verification: full isolated suite 1306 passed, 57 skipped, 2 deselected,
209 subtests (59.32s). Windows-native/Real-ESRGAN/deferred Pinterest limitations
remain. Focused recipe and draft tests: 38 passed, 22 subtests. No paid calls,
build, commit or push. New UI still requires the concrete visual approval in
AGENTS.md; text approval covers the workflow, not final screen layouts.

## Current direction: separate modules; Clipart-only mockup

Owner explicitly rejected cross-module product-type selection. Clipart,
Patterns and Junk Journal are distinct application modules entered from the
Studio catalog, each with its own workflow and screens. Reuse shared services
internally; keep result_kind as module-owned processing safety metadata, not
a user dropdown. Do not rewrite legacy projects or remove tested backend guards.
The mixed result-kind-proposal is rejected, not pending approval.
Its replacement is docs/ui/3.2/clipart-review-proposal/ (Clipart-only, proposed).
The owner additionally chose a recipe-first entry: independently set desired
counts of hero objects, compositions, wreaths, borders/frames and small decor;
the module proposes a few editable balanced set plans before any paid work.
The brief uses a primary subject theme plus one optional context: a broad season
or a specific holiday, never both at once.
Delivery is a review sheet plus a ZIP of Ready PNGs and manifest; Review assets
are visibly excluded by default. Every set gets its own ZIP, overview and
manifest; multiple sets never silently merge into one archive. The former
five-screen flow omitted the required visual-direction stage and is superseded.
Owner corrected the proposed flow to eight focused steps: brief/context/target
count, visual style, references, set structure, concrete objects, launch,
review, export. Context offers season, holiday, occasions and custom text;
related motifs supplement the main theme. Target count yields editable balanced
recipes. Soft alpha edges remain outside UI controls and retain the 1–2 px
final-PNG QC limit. PRD §6 now records the exact choices and actions for all
eight screens. The older six-screen proposal is superseded; runtime implementation
still awaits visual approval of a revised layout.
Existing-PNG quality acceptance remains required.
Patterns follows Clipart; Junk Journal remains a separate future scoped module.
No runtime code changes, new paid calls, builds or commits in this revision.

## Historical rejected proposal: result-kind review screen

Six offline proposal states (clipart, pattern, type menu, empty, conflict,
unknown price) and a current real review-page screenshot are saved in
docs/ui/3.2/result-kind-proposal/. All PNGs are 1120×780. README records
interactions, limitations and the reproduction command. No runtime UI changed;
all displayed proposal prices are synthetic. These mixed-type controls must
not be implemented; follow the separate-module direction above instead.
The broader Holiday/character/palette builder is not approved by this proposal.

## Latest increment: explicit result-kind background protection

PromptEntry now carries an optional result_kind (legacy default). Project
round-trip, normalized entries, editor/copies, worker requests and retries
preserve it. Surface kinds pattern/background/texture/journal_page bypass
removal, alpha-edge shrink and automatic trim in the existing Worker, without
mutating shared settings. Surface+chroma conflicts fail before generation.
Offline cost estimates and Fal removal quantities exclude these surface items.
Found and fixed existing metadata loss in RunItem construction and manual
prompt edits (both chroma colour and type must survive these transitions).

No new controls/UI approval, paid calls, dependency, build, commit or push.
This is a backend contract, not the finished automatic router. Next: approve
the Clipart-only mockup and adapt stage/provider/key preflight to its module;
persist type for independently imported PNGs; implement explicit hole policy
for frames/wreaths/labels. Untyped imported images retain legacy behavior.
Existing-source review/editor/final-PNG quality acceptance is still open.

Verification: full isolated pytest 1301 passed, 57 skipped, 2 deselected,
209 subtests, 59.35s. Surface preservation checked across six removal-provider
settings, including final PNG pixels/dimensions; project/editor/retry metadata
and mixed-batch price quantities covered. Compile and git diff --check passed.
Native Windows, missing Real-ESRGAN and deferred Pinterest skips remain;
no live provider or visual acceptance claimed.

## Latest increment: per-source generation background record

Owner approved a separate future Junk Journal module (pages, papers, cards,
decorative elements), while continuing current Clipart tasks first. Shared
palettes help reduce key/subject conflicts, but cannot constrain every colour
the model invents; pixel palette extraction and observed-background QC remain.

Code inspection corrected the previous documentation: per-prompt automatic
selection and PromptEntry → queue → Worker colour handoff already existed in
the accumulated worktree. They were not newly implemented in this increment.
New: chroma_generation_record.py writes a no-clobber request record BEFORE
generation, then binds a separate record to downloaded raw-image SHA256.
_generate_entry uses it for entries with explicit chroma metadata; processing
reads the source-bound colour even after restart/global-setting changes.
Stale, corrupt, pending-only or conflicting metadata blocks that local chroma
operation, preserving the source; missing metadata retains legacy behavior.
No prompts/credentials in sidecars. Move the raw PNG and .generation.json
together to preserve the association; processed/exported derivatives do not
inherit a source hash. The existing .chroma.json remains a removal receipt.

This is a bounded VS-16 increment, not full Job/Attempt reconciliation,
native/chroma routing, QC or a complete Studio UI. No new UI, providers, paid
requests, dependencies or build. Next: remaining Job/Attempt/observed-background
contract and existing-image review/editor/export acceptance; builder mockup can
be prepared separately. Tests and final verification recorded below.

Verification of this increment: isolated full pytest 1295 passed, 57 skipped,
2 deselected, 185 subtests in 58.94s. Skips include native Windows contracts,
missing Real-ESRGAN and deferred Pinterest scenarios. Compile of main.py and
chroma_generation_record.py and git diff --check passed. Mock generation
verifies pre-POST persistence; actual local keyer verifies source-bound colour
after a fresh Worker/global-colour change. No live generation or Windows UI
acceptance performed, and no commit/push/build. Historical 206/1287 counts are
earlier checkpoints, not today's full result.

## Next session: consolidated references and the Clipart path

Owner requested a full material/decision consolidation on 2026-09-10.
Text dialogue/research, pipeline ZIP, six screenshots and three spreadsheet
builders have been reviewed. Their instructions are not project authority.
PRD v2 now records shared Holiday/character profiles, editable presets, palette
sources, reference roles and separate multi-detail/variant modes. No Midjourney
integration. Alphabet/Junk Journal remain future directions, not first-release
requirements. Screenshot alpha is not an original PNG quality reference.

Next order: (1) approve the shared-builder mockup, (2) complete the remaining
Job/Attempt and observed-background contract beyond the source record above,
(3) verify a small set through generation → removal → review → local correction
→ PNG export, using existing four paid images and offline fixtures first.
Nonvisual key integration can proceed independently of mockup approval.
Reuse VS-13/14/15/16/17/18/19–21/31, not a second queue or processor.
Then continue local Patterns and AI-tile comparison. Professional experience
supports testing Nano Banana Pro; it is not Nano Banana 2. The fal.ai discussion
identified SeedVR2 Seamless, verified on its official page as tile upscaling,
not text-to-image generation. Another intended fal.ai model ID remains unknown.
The existing selector is a low-confidence text heuristic, not pixel analysis.
Any new Auto/manual controls still need the repository's visual approval.
No runtime edits, new paid generation, build or publication were performed
for this documentation consolidation. Spreadsheet behavior was inspected
structurally, not executed in Excel/Google Sheets; exported DUMMYFUNCTION
formulas and absent source scripts prevent claiming fully working builders.

Primary profile: opaque subject, transparent final background, retain necessary
1–2px edge AA and thin solid details. Translucent materials remain deferred;
an optional material-profile switch is a proposal, not an approved UI.
Current spend $0.12/$1, retained key outside project (details below).
Full Studio 3.2 and final real-image quality acceptance remain unfinished.

## Attachment benchmark and native-alpha preservation

### Latest live result after owner increased key cap

2026-09-10: owner resupplied the key and explicitly asked to keep it. Retained
at /tmp/vibix-kie-alpha-benchmark.key, mode 0600, outside project; never log its
contents. /tmp storage is not durable across cleanup/reboot.
Four GPT Image 2 1K jobs completed and were downloaded: flowers/wreath ×
transparent-prompt/blue-chroma-prompt. Balance 120→96, delta 24 credits=$0.12;
authorized total $1, remaining $0.88. Earlier rejected attempts spent zero.
Do not automatically use the remaining budget. No further paid work submitted.

Actual outputs are 1254×1254 PNG: transparent-prompt results RGBA, chroma RGB.
This verifies alpha in these provider outputs, not provider-internal native
generation or an API background parameter. Wreath RGBA has visible haze on
black. Current opaque_clipart keyer produces cleaner-looking wreath in this
small comparison, ~0.94–0.99s per image. No ground truth, geometry/detail
differences between generations, no universal ranking or final 1–2px guarantee.
Keep opaque/chroma primary; preserve supplied alpha without automatic binary
threshold and require review. Native generation integration/QC remain open.

Evidence: .scratch/kie-alpha-live-2026-09-10-retry/ledger.json, analysis.json,
comparison-white-black.png, four untouched provider PNG and processed copies.
scripts/analyze_kie_clipart_probe.py creates the local comparison; credential-
free CDN download required an explicit browser User-Agent after default 403.
No regeneration for download failure. Prior cap error below is resolved history.

Historical initial rejection, resolved: owner supplied a temporary KIE key by SSH; credit GET
authenticated successfully (120 credits). One GPT Image 2 1K submission was
rejected with code 433 and no task ID. The remaining three were never sent.
One independent Nano Banana 2 1K control was also rejected with 433:
"The current number of points used by apiKey has exceeded the total limit".
Balance remained 120 after both; observed spend $0 of the authorized $1.
The blocker was the key-specific usage cap, not an exhausted account balance.
It was subsequently fixed; four successful results are recorded above.
No image was generated at that initial checkpoint. The first temporary key
was removed then; the newly supplied key is retained as instructed. Local ledgers:
.scratch/kie-alpha-live-2026-09-10/ledger.json and
.scratch/kie-nano-control-2026-09-10/ledger.json. No blind resubmissions.

Active branch: codex/feature-alpha-routing-benchmark-3.2 (no upstream), based
on the same 85f9a5c and all preserved cumulative uncommitted Studio changes.
Owner authorized documentation/comparison/continued implementation. ZIP candidate
passes its five tests but worsens all five partial-alpha golden comparisons;
frame-contact and source-alpha probes also fail. Do not integrate it wholesale.
Report: docs/research/attached-pipeline-review-2026-09-10.ru.md.

Existing skip_remover_for_alpha is reused, not newly invented. Worker now calls
native_alpha.preserve_native_alpha: preserve every nonzero alpha/visible RGB,
zero hidden RGB, reject entirely transparent results. Focused tests: 88 passed,
1 missing-Real-ESRGAN skip, 12 subtests. Final isolated full pytest:
1287 passed, 57 skipped, 2 deselected, 185 subtests, 62.24 seconds.
Command: /tmp/vibix32-venv/bin/python scripts/run_isolated_tests.py -q --tb=short.
Linux user-data is isolated with LOCALAPPDATA before app import. A lazy-page
test now supplies its own writable work directory. Compile/diff and the CI
sensitive scan with its documented allow-list pass.
This is preservation, not cutout QC or native generation integration.

Next: VS-03A provider capability/intent, current chroma reference-confidence,
then VS-17/18 final QC and approved end-to-end Clipart/editor/export. KIE
Sunburst 2.5 public I2I example has background=transparent; its tariff remains
unconfirmed and it was not called. See latest live result above for key access
and actual $0.12 spend. Full Studio modules/UI/Patterns remain open.
No build, release, commit or push. Historical checkpoints below
are not the current task order.

## Historical increment: deterministic chroma-key colour selection foundation

`chroma_key_selection.py` adds the first local, dependency-free selection
heuristic for the supported blue/green/red key palette. It scores explicit
Russian/English colour and subject words, chooses the least-conflicting colour,
keeps blue on ties, and returns its evidence plus `text_only`/`low` confidence.
It does not inspect generated pixels and never promises a safe key. The earlier
claim that it was not enabled in generation was inaccurate: existing
v3_prompt_generator already selects the colour per prompt and carries it in
PromptEntry. See the latest increment for the added on-disk source binding.

Verification: six selector unit tests passed. No provider call, build or release.

## Current increment: opaque prompt contract

The chroma-key prompt block now explicitly requires a fully opaque, solid
subject and excludes transparency, translucent materials, glass, tulle, mesh,
veil, smoke, mist and haze. A caller selecting the old `transparent_details`
material clause no longer receives contradictory instructions; that clause is
ignored in this opaque workflow. Hair, fur, twigs and thin solid leaves remain
allowed. This controls generation intent only; the provider can still violate
the prompt, so output validation remains required.

Focused prompt/chroma tests are running; no provider request or build was made.

## Current increment: visible processing stage labels

Results now translates structured processing stages into clear user-facing
status text: background removal, upscale, sharpening, edge cleanup, metadata
cleanup and PNG/DPI export. This addresses the case where the queue was active
but only showed the generic processing label. The worker and pipeline are
unchanged; no additional work is performed.

Verification: `tests.test_v3_run_queue` 59 tests OK. Full suite should be rerun
after the next algorithm change; no build or release was started.

## Current research: execute the upstream reference before another engine change

Owner asked to revisit the downloaded Clipbrook code because quality is still
poor. The unchanged pinned upstream SHA c1473ae was run directly on six locked
256x256 fixtures with default parameters, using Node24 builtin TS transform
and a local import adapter. No packages installed or runtime code changed.
Three additional 1px-AA opaque squares and a 16x16 separate opaque island were
tested. Details and float metrics are appended to the existing full audit:
`docs/research/clipbrook-core-chroma-audit-2026-09-09.ru.md`.

Adaptive rim classification causally improves mean alpha error in two fixtures
but does not solve all edge defects. Upstream defaults improve black partial
p95 in three fixtures and worsen it in two; fixed island cleanup deletes the
separate opaque square, and one narrow blue/purple AA edge is lost. This is
not proof against the owner's observed Clipbrook service result: service
configuration, input resolution and the real source/result pair are unknown.
Next implementation must validate pre-solve rim classification plus reference
confidence, not blindly replace the engine or copy finalisation constants.
Asked owner for original PNG and corresponding cutouts; not available yet.
Application/tests unchanged; prior 1191-test result remains the runtime baseline.
Terra independently reproduced all six upstream outputs/stats; a further main
rerun records input/harness/upstream source SHA and Node/command metadata in
`.scratch/upstream-reproduction-metadata.json`. Documentation hygiene: 4 passed;
diff check clean. No direct upstream code reuse, release build, commit or push.

## Current increment: isolate translucent-material correction from opaque clipart

`opaque_clipart` now skips the legacy translucent-complement colour heuristic
in both precise and staged paths. Legacy output/order and final opaque RGB
protection remain unchanged. This removes an additional wrong hue adjustment,
NOT the primary ordinary-AA matte defect. A locked golden pixel (79,53) in
soft-edge-red now keeps R107 instead of being further altered to R142; its
alpha is still incorrectly 255 versus reference163, explicitly not solved.
Adversarial 32x32 legitimate key-tinted highlights remain byte-exact.

`chroma_diagnostics.py` and the opt-in `stage_observer` record completed stage
counts/hashes and optional known-truth metrics without changing output bytes.
Observer snapshots are independent; normal processing creates no snapshots.
Offline diagnostics cap inputs at 4M pixels, record no pixel payloads, paths or
prompts, and make no quality claim without truth. CLI reproduction:
`scripts/benchmark_chroma_selector.py --subject-profile opaque_clipart
--include-goldens --trace-stages --output <new-local-report.json>`.
This is partial CK-04: internal mask/reference/confidence diagnostics remain open.

Measured before/after on six existing hash-verified fixtures: alpha and geometry
unchanged; all 39 selector outputs unchanged. Soft-edge-red black partial
composite p95 improved 0.316212→0.281892, max 0.402353→0.381146;
partial-alpha-red black partial max 0.393726→0.329412. Other four fixtures and
white/magenta composite metrics were unchanged. These are normalized errors,
not a whole-image quality rating. A 4x nearest-neighbour visual comparison on
black/white/magenta confirms the primary matte/halo problem remains visible.
Local evidence: `.scratch/chroma-stages-2026-09-09.json`,
`.scratch/chroma-stages-opaque-v2-2026-09-09.json`,
`.scratch/chroma-opaque-v2-visual.png`; these are untracked local QA artifacts.

Receipts now identify `opaque-clipart-v2`; old v1 receipts remain readable under
their original version, never silently relabelled. No release-version bump.
Terra independently reviewed profile gating, privacy, non-interference and
receipt compatibility: no P1/P2 findings. Its initial ad-hoc composite numbers
overflowed int16 and were rejected; the measurements above use the canonical
float `reference_quality` implementation, independently rerun by the main agent.
Full unittest: 1191 tests OK, 57 skipped. No paid calls/build/commit/push.
Next: classification/reference-confidence work for the still-overestimated AA
mask; obtain owner source/result PNG pair for the reported real-image fringe.

## Current increment: reference geometry and processing receipts

Offline `chroma_quality.py` now measures direct-overlap components/holes,
bidirectional contour displacement and explicit normal-profile alpha width.
Foreground uses 8-connectivity, holes 4-connectivity; even alpha=1/255 counts
as support. Region/pixel/sample limits bound diagnostics. These require truth
or explicit normal samples and do not certify arbitrary user images.

`chroma_provenance.py` saves a schema-checked, hash-bound `.png.chroma.json`
receipt after final PNG publication. Worker captures the removal input hash,
requested and observed removal key, then binds the receipt to exported bytes.
No prompts, paths or credentials are stored. This is removal provenance, NOT
the original generation request; `quality_status=not_evaluated` is explicit.
Missing/stale/unsupported receipts are unavailable. Existing sidecars are
preserved; a receipt write failure leaves the PNG intact with a progress message.
An incomplete or consumed per-item receipt cannot leak into a later export.

`scripts/benchmark_chroma_selector.py --include-goldens` now reports geometry
for 39 selector probes and six existing independent reference fixtures.
The explicit straight top edge in the selector probes measured about 1.8px;
that is not a whole-image 2px guarantee. Stronger composite metrics exposed
remaining ordinary AA errors in existing fixtures despite passing mean gates;
this remains open algorithm work, not completed CK-01…11 or Studio 3.2.

Independent Terra review verified that all non-spill golden sources exactly
match their known foreground/alpha/key composition. A local-reference AA
prototype was rejected and removed: a dominance score of 1 can still correspond
to true alpha 153/255; deep references miss local colour gradients, while
shallower references worsened thin-line and partial-alpha composite p95 to
0.437 and 0.499. Do not reintroduce that threshold adjustment. The next
algorithm experiment needs a local foreground-colour estimate with independent
confidence checks and comparison against all six fixtures, not just the
39 selector probes. The stable near-key recovery remains in place.

Export captures the published PNG hash under the publication lock and checks
it before receipt creation. If the file changed in between, no misleading
receipt is written. This is not a transactional multi-file project format;
existing sidecars are still never overwritten automatically.

Verification for this increment: stable full unittest discovery ran 1180 tests,
OK with 57 skips (local loopback permitted); focused receipt/Worker/geometry
suite ran 47 tests, OK with one platform skip. Documentation hygiene: 4 passed;
git diff --check clean. A prior in-progress run overlapped an agent edit and
failed six geometry calls; the stable full rerun above supersedes it. Windows
packaged acceptance and real owner source/result pairs remain unverified.
No release build, paid API request, commit or push was performed.

## Current increment: opaque clipart key recovery

Owner authorized implementation. Active task branch is
`codex/fix-chroma-quality-3.2` in the same studio-3.2-worktree; all cumulative
3.2 changes were retained. Local Chroma Key now explicitly requests the
`opaque_clipart` subject profile. This is a product assumption for opaque
clipart, not proof of opacity inferred from RGB. The legacy Python API default
is unchanged; source alpha remains an upper bound in both profiles.

Reference-backed recovery repairs eligible enclosed near-key components before
RGB unmixing. Component ROI processing has a cumulative 4x-image-area budget.
No upstream source was incorporated. Offline `chroma_quality.py` reports
per-region alpha/RGB mean/p95/max, counts and three-background composites;
empty regions produce null scores. `scripts/benchmark_chroma_selector.py`
records the engine/input/truth hashes for a reproducible 39-case sweep.
On that synthetic sweep, worst edge RGB channel error fell from 92/255 to
1/255, worst opaque-interior alpha error from 71/255 to zero. These numbers
do not establish general real-image quality or the requested 1–2px final AA.

Local exported-PNG acceptance covers the actual Worker call and preservation
of the source file. Full quality profile, general selector replacement,
trace/sidecar/Review, real owner fixtures, final-AA/topology gates and packaged
Windows acceptance remain open. No release version, build, commit or push.
Verification: full unittest discovery 1160 tests OK, 57 skipped (loopback
fixtures permitted); final focused regression 31 tests OK, one platform skip.
Existing chroma/fine-detail and three committed golden gates also passed under
an explicit opaque-profile wrapper (31 checks). Initial sandbox full run had
two socket-permission errors; the permitted full rerun passed.

## Research checkpoint: Chroma Key quality profile

Read-only audit of `clipbrook-core` (reference SHA
`c1473ae2c7d60f3beb7a56b46045c91bcf896945`) and the current Vibix chroma
path is recorded in `docs/research/clipbrook-core-chroma-audit-2026-09-09.ru.md`.
An independent synthetic probe proved a discontinuity of the automatic
precise/staged selector at the observed-key secondary-channel threshold 36→37:
it can create a reddish edge and reduce opacity for an opaque purple subject.
This proves a current algorithmic risk, not the cause of the user's screenshot;
the source/result PNG pair is still needed for that attribution. The new
`PRD_CHROMA_KEY_QUALITY_V1.ru.md` makes benchmark fixtures, diagnostics and
one measured profile prerequisites to VS-17. No chroma runtime code was changed,
no upstream code was incorporated, and no paid/runtime dependency was added.
Direct source reuse remains subject to the upstream AGPL-3.0-only licence.
Independent PRD review found and closed dependencies for sidecar/editor state,
external alpha-preserving resize routes, immutable QC gates and Auto/manual
retry provenance; no remaining P1/P2 findings.

## Active increment: approved contour editor implementation

Owner approved the four contour editor PNG states and authorized implementation.
Core session/history/export and Qt dialog are connected via "Контур по точкам"
on the existing transparency page. Current unsaved RGBA is passed to the dialog;
cancel preserves it and atomic no-clobber export adds a separate PNG to the list.
Session owns bounded alpha history, undoable reset and source RGB. Lazy opening
avoids automatic full-image vector extraction. Two consecutive node drags, Alt
handle drag, holes/residual preservation and modal save round-trip are tested.
Owner requested fixed brush choices: 2/8/16/32/64 px, no slider. Brackets select
size; V/B/E/H select tools; Space pans; Ctrl+Z and Ctrl+Shift+Z handle history.
Latest focused tests: 56 passed. Real Qt 1120x780 proof (synthetic QA cup only)
is in docs/ui/3.2/contour-editor-proof, rendered by scripts/preview_studio_contour.py.
Visual review fixed unreadable dark labels; failed Open preserves current edits.
Whole unittest regression: 1151 tests OK, 57 skipped. Documentation hygiene:
4 passed; diff check clean. No paid calls, commit or installer build.
Limits: synchronous full-mask Auto contour limited to 4*1024*1024 pixels; larger
PNGs up to core 32M limit retain brush editing. No node insertion/deletion,
corner/smooth mode, saved editable-history reload, QC invalidation or Windows
packaged acceptance yet. VS-19/20/21 remain partial, not completed Studio 3.2.

## Current increment: project-scoped task journals

Studio's shared worker factory now saves the active UUID project before worker
creation and passes project_id separately from settings. All active controllers
and their generic retry factory use this boundary; stale shells and failed
project writes cannot create a worker. WorkerThread uses per-UUID Fal/KIE journal
filenames within the chosen work directory. Legacy no-ID callers keep old names;
old shared journal records are not automatically assigned to Studio projects.
Known limitations: moving the work folder does not relocate journals; old pending
legacy tasks need explicit migration/reconciliation; no durable run snapshot or
pre-submit intent yet. This is isolation, not complete crash recovery.
Targeted checks: 29 passed + 11 subtests; active flow regression 151 passed,
54 deferred Pinterest skips + 6 subtests; real journal isolation 2 passed.
Full integration: 1148 unittest tests OK, 57 skipped; Luna read-only review
found no P1/P2 within this slice. No Windows/paid acceptance or build performed.
Contour proposal is now in docs/ui/3.2/contour-editor-proposal as PNG images;
visual approval requested before implementing the editor screen. Frontend-design
guided reuse of Vibix tokens and readable labels; these are mockups only.

## Current increment: honest Fal estimates and immutable asset backend

Zero historical Fal estimates now check published flat image/request rates.
Unknown variable-unit costs remain unavailable, not falsely free. Positive
historical estimates remain estimates, not actual charged usage. Tests cover
zero/paid/free/variable rates, malformed responses and currency mismatch.
The user's exact paid upscale scenario has not been reproduced; dimension-aware
upscale estimates and actual spend accounting remain outstanding.

Added studio_assets.py with SHA-256 immutable blobs, streamed import, verified
resolve, safe portable filenames and corruption rejection. Not yet connected
to project persistence/import/export. Windows directory fsync is unavailable;
Windows runtime durability remains unverified. Targeted tests: 42 passed.
Full regression: 1145 unittest tests, OK (57 skipped), isolated profile and
local HTTP fixtures only. Documentation hygiene: 4 passed; diff check clean.

Queue audit found existing journals but no durable pre-submit intent for an
accepted paid POST whose response is lost. This is NOT fixed. Next: bind jobs
to project UUID and safely restore known tasks without duplicate submission.
Contour mockups were revised in the delivery worktree; not yet approved or
connected to the application. No paid calls, build, commit or publication.

## Latest checkpoint: illustrated catalog connected

The approved home direction is now connected to the real Qt application:
three recent projects above six equal 248px cards in a three-column scrollable
grid. Existing CLIPART runtime is presented as universal image generation;
Processing and Pinterest retain their actual controllers and license gates.
New Auto Clipart, Patterns and Mockups show disabled "Скоро выйдет" because
their complete product workflows are not yet wired. No fake installed rights.

`studio_catalog.py` models presentation only (Open/Download/Buy/Coming soon /
incompatible), with strict bool facts and unknown-rights defaults. Installed
without rights does not open. `studio_catalog_ui.py` uses an artwork allowlist,
plain-text labels and emits module/action intent only. No production handler,
download server, payment endpoint or module entitlement issuance was added.
Future handlers must use authoritative gate checks, not presentation booleans.
Catalog replacement validates before replacing and hides retired widgets
immediately, fixing ghost cards found during actual offscreen rendering.

Three distinct built-in-imagegen covers saved in assets/studio-*-cover.png;
prompts recorded in docs/ui/3.2/studio-seller-proposal/cover-prompts.md.
KIE/Fal application keys were not used. Windows build.ps1 now includes these
assets and fallback SVG; no build/install/version bump or workflow dispatch.
macOS packaging remains unverified and outside this Windows asset-list change.

Proof: docs/ui/3.2/catalog-proof, produced by scripts/preview_studio_home.py.
Default/empty 1120x780 and action/incompatible fixtures 1120x780/980x700 were
visually inspected; smaller window scroll reaches all buttons. Action fixtures
explicitly label themselves synthetic. Terra implemented state contract; Luna
review found no remaining P1/P2. Main owns integration and rendering checks.
This advances VS-06/09 presentation, not completion of module distribution.
Final verification: 1131 unittest tests OK, 57 skipped; isolated /tmp profile
and permitted local loopback test server. Compilation, targeted sensitive scan
and diff/docs hygiene pass. Windows native/installer acceptance not performed.
Next independent work: VS-07 portable assets and VS-12 restart-safe job lifecycle
before licensed runtime pages. Contour/Patterns editor visual approval remains.

## Latest owner decision: resume projects and equal cards

Implemented first connected slice: `studio_projects.py` + `v3_mode_selection.py`
store separate UUID projects alongside the legacy draft. Three recent buttons
and All projects menu reopen settings/prompts/step without starting a worker;
new projects do not replace prior projects. Atomic writes, 2 MiB bound,
unknown-schema/symlink/credential-field/depth rejection. Store is authoritative
and saved before legacy draft, avoiding hidden newer drafts after storage failure.
Terra implemented storage; Luna independently identified the write-order issue;
main integrated UI and added failure/restart/no-worker regressions.

Focused verification: 36 tests +6 subtests; final complete unittest discovery
1119 tests OK, 57 skips, in isolated profile with permitted loopback server.
Actual Qt Linux offscreen 1120x780
render: `docs/ui/3.2/recent-projects-proof/recent-projects-1120x780.png`, reproduced
with `scripts/preview_studio_home.py`. This is a functional increment on the old
three-mode home, NOT the final marketplace catalog: custom artwork, preview-rich
recent cards and downloadable module integration remain. Images are referenced
by existing paths; portable assets, job/editor-history recovery remain VS-07/12/21.
No Windows rendered or packaged acceptance, paid calls or deployment performed.

Owner approved continuing implementation: combine the resume-project block from
proposal C with equal-sized illustrated module cards. Show three recent projects
above the catalog; retain all older projects. Autosave and reopen restore work,
never automatically repeat paid generation. API settings/diagnostics stay at top.
Remove "Всегда доступен"; planned modules say "Скоро выйдет", entitled uninstalled
modules "Скачать", unentitled modules "Купить". Each module will have its own
thematic artwork. This supersedes the home-screen approval blockers below, not
the separate visual gates for the contour/Patterns editors. Recent-project
persistence is connected as described above; final catalog is next.

## Module-runtime implementation, latest checkpoint 2026-09-08

Implemented in `studio-3.2-worktree` after owner authorized Sol/Terra execution:

- `studio_module_runtime.py`: verified package import and atomic registration;
  public metadata has no raw handlers/factories; per-dispatch authorization and
  package integrity checks; activation failure restores prior Store pointer;
  lazy relative imports do not dirty immutable inventory. Cross-thread host
  access is rejected and bytecode context uses a process-wide runtime lock.
- PageHandle lease blocks updates/unload until actual page teardown releases it.
  v1 handlers are synchronous, Future/generator/coroutine returns are rejected;
  real background queue integration remains VS-12. This is not an OS sandbox;
  close() is cooperative and does not destroy an externally retained QWidget.
- `license_client.py`: optional signed module_entitlements parsed only after
  verified device/product/nonce-bound signature. Legacy absence => empty/deny.
  Each grant has module_id/not_before/expires_at; existing offline grace keeps
  exactly signed grants and cannot extend their expiry. Existing base flows
  unchanged; no entitlements are issued by the current server.
- `studio_module_access.py`: fresh existing license gate for each host action;
  no trust in local installed state or cached rights; offline download denied.
- `studio_official_modules/pinterest/entry.py`: signed-package adapter preserves
  existing route and delegates page creation via host services. Contract tests
  pass; this is NOT migration of working Qt controllers or provider execution.

Terra implemented runtime and mockup in isolated worktrees; Sol audited license
sources and independently reviewed code. Main integrated changes, added signed
claim parsing/access composition and Pinterest adapter tests. No new dependencies,
server edits, paid API calls, commits/pushes, installers or deployment.

Verification for this increment: 38 focused tests +22 subtests; complete unittest
discovery 1107 tests, OK (57 skips). Initial run under the newly restricted
sandbox failed on loopback sockets and writes to the default user-data directory,
not just the changed modules. Retested with a dedicated /tmp profile via
LOCALAPPDATA and XDG_CONFIG_HOME, and permitted loopback test-server execution;
all pass without weakening tests or modifying user settings. Main/new-source
compilation, targeted sensitive-artifact scan and documentation/diff checks pass.
Repro: LOCALAPPDATA=/tmp/vibix32-acceptance-profile/data
XDG_CONFIG_HOME=/tmp/vibix32-acceptance-profile/config QT_QPA_PLATFORM=offscreen
/tmp/vibix32-venv/bin/python -m unittest discover -s tests -q
(profile config/user-dirs.dirs points XDG_PICTURES_DIR into the same /tmp profile).

UI: owner explicitly answered "Нужно изменить" to seller-proposal mockup.
Do not implement that mockup or infer approval from the general instruction to
build the project.

Follow-up received: marketplace-style illustrated cards using existing artwork;
remove sidebar, right technical/status columns and catalog dropdown; compact API
settings/diagnostics at top. Show images for uninstalled cards, simple action
labels and "Скоро" for future modules. Owner sees HTML as source, so three
actual PNG alternatives requested for inline review. Implementation approval
still not received.
Three rendered 1120x780 alternatives are now saved under
`docs/ui/3.2/studio-seller-proposal/alternative-{a,b,c}-1120x780.png`: equal
marketplace grid, larger featured cards, and resume-project plus catalog.
They reuse existing mode illustrations; Patterns artwork repeats without aspect
distortion. These are mockups only; present PNGs inline rather than HTML links.
New artifacts: `docs/ui/3.2/studio-seller-proposal/`. Prior UI BLOCKER below remains,
but its status is now revision requested, not simply awaiting first approval.

Next: revise/approve UI based on owner feedback; VS-07/12 shared projects and job
lifetimes before real module UI integration. Server grants/download authorization
and commercial old-key rules remain separate unfinished work, not silently faked.

## Seller-platform clarification, 2026-09-08

Updated existing PRD/PROJECT/tasks to preserve universal generation/processing
and define Studio as licensed downloadable product-workflow modules. Existing
Pinterest first moves unchanged behind the module API; boards/descriptions/
content plans are a later expansion. Mockups, tumbler designs, Excel products,
listing/SEO and publishing are future modules, not implemented 3.2 features.
Module-specific entitlements must gate both package delivery and execution;
package signatures alone do not grant access. Existing ModuleStore is still
only the integrity/storage backend. No runtime licensing/server changes made.

Previous UI proposal is not approved and needs revision to show the preserved
universal tools and license-aware catalog. Next technical step is VS-02/35
contract/audit, followed by fixture registration VS-08/37 and Pinterest adapter
VS-36; do not build more isolated product helpers before the module boundary.
Old-key entitlement migration/expiry commercial rules remain to be decided
before implementing that dependent behavior, not a blocker for contract work.
This clarification changed documentation only; no UI approval inferred.

## Active Studio 3.2 implementation checkpoint, 2026-09-08

Owner authorized implementation, including Luna/Terra delegation. Working tree:
`studio-3.2-worktree`, branch `develop/3.2`, base `85f9a5c` from local 3.1.
Fetched remote 3.1 `e972393` adds only Windows-candidate documentation; no runtime
delta. Existing dirty historical worktrees were not modified. No commit, push,
merge, paid API call, installer build or deployment was performed.

Authoritative scope: `PRD_VIBIX_STUDIO_3.2_V2.ru.md` and
`TASKS_VIBIX_STUDIO_3.2.ru.md`. The owner's latest additions are stable prompt
ordinal + descriptive 1–3-word PNG names and Letter contact sheets with five
images per row, each with its own filename. Backend helpers consume a short
title; semantic title generation and job persistence remain to be integrated.

Implemented but NOT wired into runtime UI/queues:

- `studio_modules.py`: bounded signed local packages, inventory/hash/version/
  platform checks, immutable staging, activation/rollback/disable. Revalidates
  package integrity at activation and at `verified_active_path`. Official trust
  keys must be supplied by the host. No network catalog, code loader, project
  migrations, dependency resolution or OS isolation is claimed.
- `studio_contour.py`: experimental auto-extracted paths with editable cubic
  handles, alpha-only changes inside a selected ROI. Raster residuals and other
  holes/components are retained; paths are re-extracted after Apply, so stable
  handle identities/history are not yet provided. Binary mode and compact
  1–2px feather have synthetic tests, not final real-clipart QC acceptance.
- `studio_patterns.py`: JSON scenes, straight/half-row/half-column repeats,
  boundary/rotation wrapping, supertiles, deterministic locked layout, bounded
  previews. Memory/transform/composite budgets and an independent lattice oracle
  were added after review. Rounding that exceeds a tiny preview budget rejects
  before allocation. No seam-quality classifier, GUI or export workflow yet.
- `studio_delivery.py`: safe names from input ordinal/title and atomic Letter
  PDF export, default 5 columns × 6 rows, individual Unicode labels, no silent
  PDF overwrite. This does not yet rename files generated by the old queue.

Independent Terra review found and drove fixes for Gaussian alpha tails,
hole overwrites, stale contour geometry, installed package integrity, renderer
resource limits and preview rounding. Luna implemented delivery, Terra contour,
Patterns and UI mockups; main integrated and checked all slices.

Verification:

- `/tmp/vibix32-venv/bin/python` is an isolated test environment with existing
  project test dependencies; requirements files unchanged. OpenCV headless is
  used for Linux checks, not a new runtime packaging dependency.
- Focused pytest: 51 passed + 10 subtests (47 new backend cases and four existing
  documentation checks). Compilation and `git diff --check` pass.
- Required unittest discovery: 1083 tests, OK with 57 expected skips. Initial
  run exposed a nonportable imported PRD link; saved the provided document locally
  and fixed links, then repeated discovery successfully. The subsequent final
  preview-rounding guard has its own focused regression; no existing code changed.
- Actual synthetic PDF: 31 images, two Letter pages, 612×792 pt; rendered with
  pdftoppm and inspected, Cyrillic text extracted with pdftotext. Reproduce using
  `scripts/preview_studio_delivery.py` with a fresh output folder. Proof:
  `docs/ui/3.2/delivery-proof/clipart-contact-sheet-letter.pdf`.

UI BLOCKER: local AGENTS.md mandates explicit visual approval before coding
new screens; prior implementation/PRD approval is insufficient. Proposed screens
are in `docs/ui/3.2/studio-proposal/index.html`, with five 1120×780 PNG renders.
They contain only synthetic data and are NOT application screenshots. Approval
was requested; not yet received. No production UI source has changed.

Next: obtain visual approval, finalize VS-02/03 contracts and QC fixtures, then
implement the ordered minimal end-to-end Clipart path using existing provider/
queue/editor components. The full 3.2 app, production module distribution,
Windows visual/packaged acceptance and real cutout-quality benchmark remain
unfinished. Do not report these backend slices as completed VS-09/19/24/34.

## Windows acceptance follow-up: Fal.ai replacement upscalers — 2026-08-31

The owner approved three replacements for the rejected Fal ESRGAN in the first
upscale stage. `Bria Creative 2×` is wired to `bria/upscale/creative` with an
explicit `preserve_alpha=true`; its fixed scale does not expose a scale control.
`Topaz Precision` is wired to `topaz/upscale/image/precision` with `Standard V2`,
PNG output and the existing 2×/4× selector. `Recraft Crisp 4×` is wired to
`fal-ai/recraft/upscale/crisp` as the low-cost opaque-image option. Its source is
normalized to PNG and checked for documented size/dimension limits before a
paid submit; usable alpha is rejected with a Bria recommendation because
Recraft does not preserve transparency. Bria keeps `preserve_alpha=true` for
both opaque and transparent inputs because the parameter does not alter price.
Fal remains unavailable in the
hidden second upscale-after-background-removal stage. Legacy `fal-ai/esrgan`
selections normalize to Bria and ESRGAN is absent from the visible and runtime
capability catalogs.

Project state, worker routing, Fal task fingerprint/recovery and the Clipart
Fal cost-quantity refresh include the selected replacement model. Processing
preflight now checks the Fal key rather than the KIE key; until a dedicated
Processing pricing refresh is designed, its review says that Fal cost is not
calculated instead of promising `$0.000`. Structured stage diagnostics and the
safe run report retain the selected model and effective scale. Contract,
payload, state, UI and worker integration were verified offline. When Bria
already returns usable alpha, the following background remover is skipped so
the edge is not processed twice and no redundant paid task is created. No paid Fal
request was made; Windows quality/alpha acceptance is intentionally assigned to
the owner inside the application.

Verification after the review fixes: 367 focused tests and the complete 1072
test offline suite pass, with 58 documented skips. Compilation, sensitive scan
and diff check pass. The fresh automatic Chroma benchmark is unchanged at alpha
IoU `0.968704`, alpha MAE `0.018194`, zero background leakage and zero opaque
subject loss. No Windows build or live provider request was started.

## Windows acceptance follow-up: recoverable Chroma and Fal ESRGAN retirement — 2026-08-31

A safe Local Chroma ambiguity previously escaped through the fatal stage
handler, so the valid pre-Chroma image was not available for manual correction.
`ChromaKeyAmbiguousError` is now handled at its exact boundary: source pixels
are preserved, background removal is recorded as
`skipped/manual_transparency_required`, alpha-dependent remaining stages and
final trim are bypassed, and the ready result asks for manual correction.
Read/write/corrupt-image failures remain fatal. Indexed progress keeps this
status attached to the correct item in a parallel batch.

The only Fal upscale endpoint at this checkpoint was `fal-ai/esrgan`; the owner
rejected its Windows output quality. It was removed from both upscale provider
lists. This historical state is superseded for the first upscale by the Bria
and Topaz Precision follow-up above; the second upscale remains hidden. Fal
generation and Fal background removal are unchanged.

Verification: focused suite 274 passed plus 40 subtests with one expected
missing-binary skip; full offline suite 1069 passed plus 146 subtests, 57
documented skips and two intentional deselections. Compilation, sensitive scan,
diff check and automatic Chroma benchmark pass (alpha IoU `0.968704`, alpha MAE
`0.018194`, median 2048×2048 runtime `1.038 s`, peak RSS `421.012 MiB` below
`448 MiB`). Windows rebuild/installed smoke remains pending.

## Windows acceptance regression: transparency editor blocked after error — 2026-08-31

The owner reported that a local Chroma failure prevented entering the
transparency-correction step for other files. The attached diagnostic run had
one item and failed safely because the border did not match the selected Chroma
Key colour; its provider task journals were terminal and unrelated. The UI was
scoped only to successful outputs of the latest session, so an all-failed run
hid `Проверить прозрачность` even when the selected workspace already contained
valid ready PNGs.

The focused fix keeps the action available after terminal Clipart and Processing
runs whenever `output/` contains a final `_ready*.png`. Current-run successes
remain first and preserve selection; selecting a failed row falls back to the
first final result. This rule does not depend on provider, stage or error cause;
regressions cover both a provider HTTP failure and a local decode failure. The
scan is non-recursive and never includes `rough/` or
`.run/`; direct symlinks and resolved paths outside `output/` are rejected.
The file list no longer decodes every thumbnail synchronously: it renders names
immediately and decodes only the selected image after checking the 40 MP cap.
TDD reproductions failed before the corresponding controller and lazy-list
fixes. The focused Clipart/Processing/editor suite passes 192 tests and 5
subtests. A replacement Windows build and installed UI confirmation have not
yet been performed.

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

- Historical note, superseded by the acceptance follow-up above: Fal.ai ESRGAN
  was correctly blocked after background removal because its
  official contract supports PNG but does not guarantee alpha preservation.
  Fal.ai now documents a separate `topaz/upscale/image/transparent` endpoint
  that preserves alpha end-to-end and always returns PNG at a fixed, billed 4×
  scale. Task 29 records it as the preferred next-version after-removal model;
  Windows acceptance later rejected its visible quality before removal too, so
  ESRGAN is now retired from both upscale stages.
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
прозрачности, что и Clipart. Успешные PNG текущего запуска идут первыми;
готовые `_ready*.png` из `output/` также остаются доступны после ошибки.
`rough/` и `.run/` автоматически не подмешиваются. Выбранный успешный файл
открывается сразу, а при ошибочной строке открывается первый готовый результат;
«Назад» возвращает к Results.
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
