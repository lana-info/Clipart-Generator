# Pinterest Pins Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Реализовать отдельный Pinterest Pins workflow, который создаёт три безопасных шаблонных пина и три AI-сцены из фото товара, сохраняя исходный товар и его точный рисунок.

**Architecture:** Pinterest Pins получает собственный draft с фото товара, текстом и параметрами серии. Шаблонный renderer и AI-scene renderer производят независимые артефакты размера 1000×1500; исходный товар хранится как защищённый слой и композитится поверх фона. Существующие очередь, локализация, provider registry, экспорт и сохранение проекта переиспользуются через тонкие адаптеры, а Pinterest не получает clipart-only controls.

**Tech Stack:** Python 3.11+, PyQt6, Pillow, существующие `ProjectState`, `ClipartRunRequest`/worker adapter, provider registry, pytest/offscreen Qt tests.

**Spec:** `docs/superpowers/specs/2026-08-28-pinterest-pins-design.md`

## Global Constraints

- Вертикальный формат: 2:3, по умолчанию 1000×1500 px.
- Один запуск создаёт ровно 6 вариантов: 3 template и 3 AI-scene.
- Исходный товар остаётся защищённым source layer; AI не перерисовывает его по умолчанию.
- Сохраняются цвет, материал, текстура, пропорции, логотипы, надписи и точный паттерн товара.
- Перегенерация может менять только фон, сцену или layout, но не source product layer.
- Все принятые результаты сохраняются в выбранную папку как JPG/PNG.
- Контент-план, SEO, расписание, публикация в Pinterest и полноценный Canva-редактор не входят в MVP.
- Clipart schema и clipart-only transparency/background controls не должны появиться в Pinterest UI.
- Не добавлять зависимости без необходимости; существующие provider abstractions и локализация обязательны.
- Сетевые AI-вызовы должны быть opt-in, bounded, отменяемыми и покрытыми network-free tests.

---

## File Map

- Modify: `v3_project_state.py` — Pinterest draft fields for product inputs, pin copy, series settings, and result metadata.
- Modify: `pinterest_prompt_schema.py` — add validated scene/layout render inputs without importing Clipart fields.
- Create: `pinterest_pin_templates.py` — deterministic template layouts and text-safe placement contracts.
- Create: `pinterest_pin_composer.py` — protected product-layer compositing, alpha/mask handling, canvas export, and fidelity guards.
- Modify: `v3_pinterest_flow.py` — Pinterest-specific input, preview, generation orchestration, selective scene regeneration, and folder export.
- Modify: `v3_clipart_flow.py` or shared worker adapter only where a provider-neutral request hook is required; do not fork the Clipart pipeline.
- Modify: `workflow_definitions.py` — explicitly describe Pinterest Pins pages and allowed operations.
- Modify: `v3_provider_registry.py` only if a capability flag is needed for scene/background generation; do not expose Clipart-only processing controls.
- Test: `tests/test_pinterest_prompt_schema.py`, `tests/test_pinterest_pin_templates.py`, `tests/test_pinterest_pin_composer.py`, `tests/test_v3_pinterest_flow.py`, and relevant state/workflow tests.
- Modify: `TASKS_3.0.ru.md`, `STATE.md` — record implementation status and remaining content-module scope.

## Task 1: Extend the Pinterest draft contract

**Files:**

- Modify: `v3_project_state.py`
- Modify: `pinterest_prompt_schema.py`
- Test: `tests/test_v3_project_state.py`, `tests/test_pinterest_prompt_schema.py`

**Interfaces:**

- `PinterestModeData` produces a serializable draft consumed by `v3_pinterest_flow.py`.
- Add `PinterestPinData` or equivalent fields with these exact defaults:

```python
canvas_width: int = 1000
canvas_height: int = 1500
template_count: int = 3
ai_scene_count: int = 3
product_paths: list[str] = field(default_factory=list)
selected_product_index: int = 0
pin_title: str = ""
pin_subtitle: str = ""
pin_cta: str = ""
style: str = ""
background_description: str = ""
color_palette: str = ""
```

- Result metadata must include `variant_id`, `variant_kind`, `source_product_path`, `output_path`, and `accepted` without storing image bytes in project JSON.

- [ ] Step 1: Add failing round-trip tests for defaults, bounds, old Pinterest projects, and rejection of invalid dimensions/counts.
- [ ] Step 2: Run `pytest tests/test_v3_project_state.py tests/test_pinterest_prompt_schema.py -q`; confirm the new tests fail for missing fields.
- [ ] Step 3: Implement bounded normalization and JSON round-trip. Preserve old drafts by supplying defaults when new fields are absent.
- [ ] Step 4: Add schema fields for `scene`, `layout`, `text`, and `restrictions` while keeping the existing renderer language-aware.
- [ ] Step 5: Run the focused tests and confirm PASS.
- [ ] Step 6: Commit `feat: define Pinterest Pins draft contract`.

## Task 2: Build deterministic safe template layouts

**Files:**

- Create: `pinterest_pin_templates.py`
- Test: `tests/test_pinterest_pin_templates.py`

**Interfaces:**

```python
@dataclass(frozen=True, slots=True)
class PinTemplateSpec:
    template_id: str
    product_box: tuple[int, int, int, int]
    text_box: tuple[int, int, int, int]
    background_kind: str

def pinterest_template_specs() -> tuple[PinTemplateSpec, ...]: ...

def render_template_pin(
    product_rgba: Image.Image,
    *,
    title: str,
    subtitle: str,
    cta: str,
    template_id: str,
    width: int = 1000,
    height: int = 1500,
) -> Image.Image: ...
```

- [ ] Step 1: Write tests asserting exactly three stable template IDs, 1000×1500 output, non-overlapping text/product boxes, and deterministic pixels for the same inputs.
- [ ] Step 2: Run `pytest tests/test_pinterest_pin_templates.py -q`; confirm FAIL.
- [ ] Step 3: Implement three layouts: product hero, editorial card, and collage. Use Pillow only and keep the product layer untouched after placement.
- [ ] Step 4: Implement text fitting with bounded font sizes and clipping prevention; never draw text over the protected product box.
- [ ] Step 5: Run the focused tests and confirm PASS.
- [ ] Step 6: Commit `feat: add deterministic Pinterest pin templates`.

## Task 3: Implement protected product compositing and fidelity guards

**Files:**

- Create: `pinterest_pin_composer.py`
- Test: `tests/test_pinterest_pin_composer.py`

**Interfaces:**

```python
@dataclass(frozen=True, slots=True)
class ProductLayer:
    source_path: str
    rgba: Image.Image
    alpha_mask: Image.Image

def load_product_layer(path: str, *, background_provider: str = "local_rembg") -> ProductLayer: ...

def composite_product(
    background: Image.Image,
    product: ProductLayer,
    *,
    box: tuple[int, int, int, int],
    add_shadow: bool = True,
) -> Image.Image: ...

def assert_product_pixels_preserved(
    source: Image.Image,
    result: Image.Image,
    *,
    product_box: tuple[int, int, int, int],
) -> None: ...

def save_pin(image: Image.Image, path: str, *, format: str) -> str: ...
```

- [ ] Step 1: Write tests that prove source RGB pixels inside the product mask remain unchanged after compositing, alpha remains present, output is 1000×1500, and unsafe output formats are rejected.
- [ ] Step 2: Run `pytest tests/test_pinterest_pin_composer.py -q`; confirm FAIL.
- [ ] Step 3: Implement source loading, local/provider-neutral alpha-mask acquisition, protected RGBA compositing, optional shadow outside the mask, and atomic export.
- [ ] Step 4: Ensure resize uses the product layer as the source and never runs a generative image-to-image transformation on it.
- [ ] Step 5: Implement fidelity guard diagnostics with counts/locations only; do not log image bytes, prompts, secrets, or full private paths.
- [ ] Step 6: Run the focused tests and confirm PASS.
- [ ] Step 7: Commit `feat: preserve Pinterest product pixels during compositing`.

## Task 4: Add Pinterest-specific input and preview UI

**Files:**

- Modify: `v3_pinterest_flow.py`
- Modify: `v3_wizard.py` only if a shared page registration hook is required
- Test: `tests/test_v3_pinterest_flow.py`

**Interfaces:**

- Add `PinterestProductInputPage` for product files, title/subtitle/CTA, style, scene description, and output folder.
- Add `PinterestPinPreviewPage` with a six-item result grid and controls:

```python
def regenerate_variant(self, variant_id: str) -> None: ...
def set_variant_accepted(self, variant_id: str, accepted: bool) -> None: ...
def export_accepted(self) -> tuple[str, ...]: ...
```

- [ ] Step 1: Add offscreen tests asserting Pinterest shows product upload, text fields, preview/export controls, and does not show Clipart transparency/background-cleanup controls.
- [ ] Step 2: Run `pytest tests/test_v3_pinterest_flow.py -q`; confirm FAIL.
- [ ] Step 3: Implement input binding to the Pinterest draft with localized labels and existing folder selection patterns.
- [ ] Step 4: Implement preview cards with source/variant labels, acceptance state, and a visible fidelity warning when the result is not composited from the protected layer.
- [ ] Step 5: Implement text-only edits without regenerating product pixels.
- [ ] Step 6: Run focused UI tests and confirm PASS.
- [ ] Step 7: Commit `feat: add Pinterest Pins input and preview pages`.

## Task 5: Generate three safe templates and three protected AI scenes

**Files:**

- Modify: `v3_pinterest_flow.py`
- Modify: shared provider request adapter only if required to generate a background artifact
- Test: `tests/test_v3_pinterest_flow.py`, provider payload tests

**Interfaces:**

```python
def build_pinterest_pin_series(
    draft: PinterestPinData,
    *,
    product: ProductLayer,
    generate_background: Callable[[str, int], Image.Image] | None = None,
) -> tuple[PinVariant, ...]: ...
```

`PinVariant` must contain `variant_id`, `variant_kind` (`template` or `ai_scene`), `image`, `source_product_path`, and `scene_prompt` without embedding secrets.

- [ ] Step 1: Add tests with a fake background generator asserting six outputs, exactly three of each kind, stable IDs, and no network calls.
- [ ] Step 2: Run the focused tests; confirm FAIL.
- [ ] Step 3: Implement template generation through `pinterest_pin_templates.py`.
- [ ] Step 4: Implement AI-scene prompts that describe only background/environment and reserve a product placement area; do not pass the product through unconstrained image-to-image regeneration.
- [ ] Step 5: Composite each returned background with the same protected `ProductLayer` and run the fidelity guard before marking it previewable.
- [ ] Step 6: Add bounded cancellation and failure handling: a failed scene leaves the three template results available and does not erase successful files.
- [ ] Step 7: Run focused tests and confirm PASS.
- [ ] Step 8: Commit `feat: generate protected Pinterest pin series`.

## Task 6: Add selective scene regeneration and folder export

**Files:**

- Modify: `v3_pinterest_flow.py`
- Modify: existing export/result queue adapter as needed
- Test: `tests/test_v3_pinterest_flow.py`, export tests

**Interfaces:**

```python
def regenerate_variant(self, variant_id: str) -> None:
    """Regenerate only the selected background/layout and reuse ProductLayer."""

def export_accepted(self) -> tuple[str, ...]:
    """Save accepted variants and return absolute output paths."""
```

- [ ] Step 1: Add tests proving regeneration changes the fake background request but reuses the same product source path and pixel digest.
- [ ] Step 2: Run the focused test; confirm FAIL.
- [ ] Step 3: Implement variant-level regeneration with a fresh bounded request and no full-series restart.
- [ ] Step 4: Implement safe filenames such as `<product>_template_01.jpg` and `<product>_ai-scene_01.jpg`, collision-safe within the selected folder.
- [ ] Step 5: Export only accepted variants, preserve successful files after partial failures, and show a summary with saved count and folder.
- [ ] Step 6: Run focused tests and confirm PASS.
- [ ] Step 7: Commit `feat: export and selectively regenerate Pinterest pins`.

## Task 7: Wire workflow, localization, and provider capabilities

**Files:**

- Modify: `workflow_definitions.py`
- Modify: `v3_pinterest_flow.py`
- Modify: localization/message registry files used by the project
- Test: `tests/test_workflow_definitions.py`, `tests/test_v3_pinterest_flow.py`

- [ ] Step 1: Add tests for the Pinterest Pins route and localized Russian/English labels, validation errors, accessibility names, and absent Clipart-only controls.
- [ ] Step 2: Run focused tests; confirm FAIL.
- [ ] Step 3: Register the Pinterest Pins pages and allowed operations without exposing transparency cleanup, clipart processing controls, or content-plan fields.
- [ ] Step 4: Route provider selection through capabilities; if a provider cannot produce a background artifact or protect the product, use the safe template path and show an actionable message.
- [ ] Step 5: Add localized messages for missing product photo, unsupported output folder, failed scene generation, and partial export.
- [ ] Step 6: Run focused tests and confirm PASS.
- [ ] Step 7: Commit `feat: wire Pinterest Pins workflow and localization`.

## Task 8: Full verification and documentation handoff

**Files:**

- Modify: `TASKS_3.0.ru.md`
- Modify: `STATE.md`
- Test: all relevant test files

- [ ] Step 1: Run `pytest tests/test_pinterest_prompt_schema.py tests/test_pinterest_pin_templates.py tests/test_pinterest_pin_composer.py tests/test_v3_pinterest_flow.py tests/test_v3_project_state.py tests/test_workflow_definitions.py -q`.
- [ ] Step 2: Run `/root/projects/Clipart\\ Generator/commit-worktree/.venv/bin/python -m py_compile main.py v3_pinterest_flow.py pinterest_prompt_schema.py pinterest_pin_templates.py pinterest_pin_composer.py`.
- [ ] Step 3: Run the full `/root/projects/Clipart\\ Generator/commit-worktree/.venv/bin/python -m pytest -q` suite and record expected platform skips separately.
- [ ] Step 4: Perform an offscreen UI smoke test that creates a six-item fake series and checks output dimensions, files, acceptance states, and no product-pixel mutation.
- [ ] Step 5: Update task status and state with exact test counts, remaining limitations, and no claim of live provider quality before a controlled run.
- [ ] Step 6: Run `git diff --check`, inspect changed files and diff, then create a final checkpoint commit `test: verify Pinterest Pins workflow`.

## Out of Scope After This Plan

- Pinterest content calendar and SEO keyword strategy.
- Automatic publishing, scheduling, analytics, or account integration.
- Canva-compatible editable designs.
- Freeform layer editor.
- Claiming pixel-perfect fidelity for an unconstrained AI-generated product image.

