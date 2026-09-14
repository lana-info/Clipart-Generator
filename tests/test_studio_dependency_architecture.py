"""Architecture dependency baseline for the incremental Studio module refactor."""
from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OFFICIAL_MODULES_ROOT = ROOT / "studio_official_modules"
BUILTIN_WORKFLOWS_ROOT = ROOT / "studio_builtin_workflows"

LEGACY_LAYER_MODULES = {
    "clipart": frozenset({
        "clipart_prompt_generator",
        "clipart_project_state",
        "clipart_run_results",
        "clipart_prompt_schema",
        "studio_alpha_qc",
        "studio_bundle_planner",
        "studio_clipart_builder_ui",
        "studio_clipart_objects",
        "studio_clipart_planner",
        "studio_clipart_recipe",
        "studio_clipart_references",
        "studio_commercial_prompt_guidance",
        "studio_export_membership",
        "studio_holiday_profiles",
        "studio_object_editor",
        "studio_palette_library",
        "studio_planning_ui",
        "studio_reference_editor",
        "studio_set_export",
        "studio_set_export_ui",
        "studio_style_profiles",
        "studio_text_client",
        "studio_text_models",
        "v3_clipart_flow",
    }),
    "pinterest": frozenset({
        "pinterest_pin_composer",
        "pinterest_pin_templates",
        "pinterest_prompt_schema",
        "v3_pinterest_flow",
    }),
    "patterns": frozenset({"studio_patterns"}),
    "processing": frozenset({
        "v3_evidence_center",
        "v3_processing_editor",
        "v3_processing_flow",
    }),
}

# Exact reviewed legacy debt at baseline 8ff2c54. Remove entries as those
# dependencies disappear; any new edge requires explicit architectural review.
LEGACY_ALLOWED_EDGES: frozenset[tuple[str, str]] = frozenset({
    ('clipart_prompt_generator', 'chroma_key'),
    ('clipart_prompt_generator', 'chroma_key_selection'),
    ('clipart_prompt_generator', 'prompt_translation'),
    ('clipart_prompt_generator', 'v3_project_state'),
    ('clipart_prompt_generator', 'v3_prompt_generator'),
    ('clipart_run_results', 'result_background_policy'),
    ('clipart_prompt_schema', 'v3_project_state'),
    ('pinterest_pin_composer', 'main'),
    ('studio_clipart_builder_ui', 'v3_project_state'),
    ('studio_clipart_objects', 'v3_project_state'),
    ('studio_planning_ui', 'studio_text_pricing'),
    ('studio_planning_ui', 'v3_api_settings'),
    ('studio_set_export', 'studio_delivery'),
    ('studio_text_client', 'studio_text_errors'),
    ('v3_clipart_flow', 'chroma_key'),
    ('v3_clipart_flow', 'chroma_key_selection'),
    ('v3_clipart_flow', 'fal_model_catalog'),
    ('v3_clipart_flow', 'license_client'),
    ('v3_clipart_flow', 'main'),
    ('v3_clipart_flow', 'model_catalog'),
    ('v3_clipart_flow', 'output_naming'),
    ('v3_clipart_flow', 'v3_api_settings'),
    ('v3_clipart_flow', 'v3_image_generation_runtime'),
    ('v3_clipart_flow', 'v3_image_generation_ui'),
    ('v3_clipart_flow', 'v3_image_review_ui'),
    ('v3_clipart_flow', 'v3_image_processing_ui'),
    ('v3_clipart_flow', 'v3_prompt_editor_ui'),
    ('v3_clipart_flow', 'v3_lazy_loading'),
    ('v3_clipart_flow', 'v3_project_state'),
    ('v3_clipart_flow', 'v3_prompt_csv_import'),
    ('v3_clipart_flow', 'v3_prompt_generator'),
    ('v3_clipart_flow', 'v3_provider_registry'),
    ('v3_clipart_flow', 'v3_run_queue'),
    ('v3_clipart_flow', 'v3_transparency_preview'),
    ('v3_clipart_flow', 'studio_workflow_host'),
    ('v3_clipart_flow', 'workflow_definitions'),
    ('v3_evidence_center', 'metadata_cleanup'),
    ('v3_evidence_center', 'metadata_inspector'),
    ('v3_evidence_center', 'v3_project_state'),
    ('v3_evidence_center', 'watermark_status'),
    ('v3_pinterest_flow', 'license_client'),
    ('v3_pinterest_flow', 'v3_api_settings'),
    ('v3_pinterest_flow', 'v3_image_generation_runtime'),
    ('v3_pinterest_flow', 'v3_image_generation_ui'),
    ('v3_pinterest_flow', 'v3_image_review_ui'),
    ('v3_pinterest_flow', 'v3_image_processing_ui'),
    ('v3_pinterest_flow', 'v3_prompt_editor_ui'),
    ('v3_pinterest_flow', 'v3_lazy_loading'),
    ('v3_pinterest_flow', 'v3_localization'),
    ('v3_pinterest_flow', 'v3_project_state'),
    ('v3_pinterest_flow', 'v3_prompt_generator'),
    ('v3_pinterest_flow', 'v3_run_queue'),
    ('v3_pinterest_flow', 'studio_workflow_host'),
    ('v3_pinterest_flow', 'workflow_definitions'),
    ('v3_processing_editor', 'v3_image_processing_ui'),
    ('v3_processing_editor', 'v3_project_state'),
    ('v3_processing_flow', 'config_schema'),
    ('v3_processing_flow', 'license_client'),
    ('v3_processing_flow', 'main'),
    ('v3_processing_flow', 'output_naming'),
    ('v3_processing_flow', 'processing_contract'),
    ('v3_processing_flow', 'v3_image_processing_ui'),
    ('v3_processing_flow', 'v3_lazy_loading'),
    ('v3_processing_flow', 'v3_project_state'),
    ('v3_processing_flow', 'v3_provider_registry'),
    ('v3_processing_flow', 'v3_run_queue'),
    ('v3_processing_flow', 'v3_transparency_preview'),
    ('v3_processing_flow', 'studio_workflow_host'),
    ('v3_processing_flow', 'workflow_definitions'),
})


def _module_name(path: Path) -> str:
    parts = list(path.relative_to(ROOT).with_suffix("").parts)
    if parts and parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def _layer_for(module_name: str) -> str | None:
    parts = module_name.split(".")
    if parts[0] in {"studio_module_api", "studio_asset_api", "studio_provider_api", "studio_job_api", "studio_project_api"}:
        return "public_api"
    if parts[0] in {
        "v3_flow_runtime", "v3_flow_ui", "v3_image_worker_settings",
        "provider_upscale_contract", "provider_error_messages", "security_redaction",
        "v3_components",
    }:
        return "shared_api"
    if parts[0] == "studio_builtin_workflows":
        if len(parts) == 1:
            return "builtin_registry"
        module_id = parts[1]
        return module_id if module_id in LEGACY_LAYER_MODULES else f"builtin:{module_id}"
    if parts[0] == "studio_official_modules" and len(parts) >= 2:
        return f"official:{parts[1]}"
    root_name = parts[0]
    for layer, modules in LEGACY_LAYER_MODULES.items():
        if root_name in modules:
            return layer
    if (ROOT / f"{root_name}.py").is_file():
        return "core"
    return None


def _production_sources() -> tuple[Path, ...]:
    sources = list(ROOT.glob("*.py"))
    for package_root in (OFFICIAL_MODULES_ROOT, BUILTIN_WORKFLOWS_ROOT):
        if package_root.is_dir():
            sources.extend(
                path for path in package_root.rglob("*.py")
                if "__pycache__" not in path.parts
            )
    return tuple(sorted(sources))


def _imports_from_source(
    source_module: str,
    source_text: str,
    *,
    is_package: bool = False,
    filename: str = "<source>",
) -> set[str]:
    tree = ast.parse(source_text, filename=filename)
    imports: set[str] = set()
    package_parts = source_module.split(".") if is_package else source_module.split(".")[:-1]
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0:
                if node.module == "studio_official_modules":
                    for alias in node.names:
                        imported = "__star__" if alias.name == "*" else alias.name
                        imports.add(f"studio_official_modules.{imported}")
                elif node.module:
                    imports.add(node.module)
                continue
            ascend = node.level - 1
            if ascend > len(package_parts):
                continue
            base = package_parts[: len(package_parts) - ascend]
            if node.module:
                targets = [(*base, *node.module.split("."))]
            else:
                targets = [
                    (*base, *("__star__" if alias.name == "*" else alias.name).split("."))
                    for alias in node.names
                ]
            for target in targets:
                if target:
                    imports.add(".".join(target))
    return imports


def _imports(path: Path) -> set[str]:
    return _imports_from_source(
        _module_name(path),
        path.read_text(encoding="utf-8"),
        is_package=path.name == "__init__.py",
        filename=str(path),
    )


def _cross_layer_edges() -> frozenset[tuple[str, str]]:
    edges: set[tuple[str, str]] = set()
    for path in _production_sources():
        source = _module_name(path)
        source_layer = _layer_for(source)
        if source_layer is None:
            raise AssertionError(f"Unclassified production source: {source}")
        for target in _imports(path):
            target_layer = _layer_for(target)
            if target_layer is None or target_layer == source_layer:
                continue
            # Importing the public API is the intended dependency direction.
            # The reverse direction remains visible and therefore forbidden.
            if target_layer in {"public_api", "shared_api"}:
                continue
            edges.add((source, target))
    return frozenset(edges)


def _format_edges(edges: set[tuple[str, str]] | frozenset[tuple[str, str]]) -> str:
    lines = []
    for source, target in sorted(edges):
        lines.append(
            f"{source} [{_layer_for(source)}] -> {target} [{_layer_for(target)}]"
        )
    return "\n".join(lines)


def test_legacy_dependency_edges_match_exact_allowlist():
    actual = _cross_layer_edges()
    added = actual - LEGACY_ALLOWED_EDGES
    removed = LEGACY_ALLOWED_EDGES - actual
    assert not added and not removed, (
        "Studio dependency baseline changed.\n"
        f"Unreviewed new edges:\n{_format_edges(added) or 'none'}\n"
        f"Stale allowlist edges to remove:\n{_format_edges(removed) or 'none'}"
    )


def test_legacy_allowlist_uses_only_exact_module_pairs():
    wildcard_characters = set("*?[]{}")
    for edge in LEGACY_ALLOWED_EDGES:
        assert isinstance(edge, tuple) and len(edge) == 2
        source, target = edge
        assert source and target
        assert not wildcard_characters.intersection(source)
        assert not wildcard_characters.intersection(target)


def test_declared_legacy_module_sources_exist():
    missing = {
        module
        for modules in LEGACY_LAYER_MODULES.values()
        for module in modules
        if not (ROOT / f"{module}.py").is_file()
    }
    assert not missing, f"Architecture layer map contains missing sources: {sorted(missing)}"


def test_relative_import_resolution_keeps_official_module_boundaries_visible():
    source = "studio_official_modules.pinterest.entry"
    assert _imports_from_source(source, "from .helper import render\n") == {
        "studio_official_modules.pinterest.helper"
    }
    assert _imports_from_source(source, "from ..patterns import scene\n") == {
        "studio_official_modules.patterns"
    }
    assert _imports_from_source(source, "from .. import patterns\n") == {
        "studio_official_modules.patterns"
    }
    assert _imports_from_source(source, "from studio_official_modules import patterns\n") == {
        "studio_official_modules.patterns"
    }


def test_package_init_uses_the_package_module_name():
    path = ROOT / "studio_official_modules" / "pinterest" / "__init__.py"
    assert _module_name(path) == "studio_official_modules.pinterest"


def test_public_module_api_is_classified_as_its_own_dependency_boundary():
    assert _layer_for("studio_module_api") == "public_api"
    local_dependencies = {
        target for target in _imports(ROOT / "studio_module_api.py")
        if _layer_for(target) is not None
    }
    assert local_dependencies == set()


def test_public_asset_api_is_classified_as_its_own_dependency_boundary():
    assert _layer_for("studio_asset_api") == "public_api"
    local_dependencies = {
        target for target in _imports(ROOT / "studio_asset_api.py")
        if _layer_for(target) is not None
    }
    assert local_dependencies == set()


def test_builtin_workflow_adapters_are_scanned_in_their_module_layers():
    clipart_entry = ROOT / "studio_builtin_workflows" / "clipart" / "entry.py"
    assert clipart_entry in _production_sources()
    assert _layer_for("studio_builtin_workflows.clipart.entry") == "clipart"
    assert _layer_for("studio_builtin_workflows.pinterest.entry") == "pinterest"
    assert _layer_for("studio_builtin_workflows.processing.entry") == "processing"


def test_public_provider_and_job_apis_are_isolated_dependency_boundaries():
    for module_name in ("studio_provider_api", "studio_job_api", "studio_project_api"):
        assert _layer_for(module_name) == "public_api"
        local_dependencies = {
            target for target in _imports(ROOT / f"{module_name}.py")
            if _layer_for(target) is not None
        }
        assert local_dependencies == set()


def test_processing_flow_does_not_import_clipart_implementation():
    imports = _imports(ROOT / "v3_processing_flow.py")
    assert "v3_clipart_flow" not in imports


def test_neutral_workflow_primitives_are_shared_api_boundaries():
    for module_name in ("v3_flow_runtime", "v3_flow_ui", "v3_image_worker_settings"):
        assert _layer_for(module_name) == "shared_api"


def test_pinterest_clipart_import_is_temporarily_limited_to_shared_page_bases():
    path = ROOT / "v3_pinterest_flow.py"
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "v3_clipart_flow":
            imported.update(alias.name for alias in node.names)
    assert imported == set()


def test_clipart_and_pinterest_use_shared_image_processing_ui_not_processing_module():
    for filename in ("v3_clipart_flow.py", "v3_pinterest_flow.py"):
        imports = _imports(ROOT / filename)
        assert "v3_processing_editor" not in imports
        assert "processing_cleanup" not in imports
        assert "v3_image_processing_ui" in imports


def test_core_prompt_generator_does_not_import_clipart_schema():
    assert "clipart_prompt_schema" not in _imports(ROOT / "v3_prompt_generator.py")


def test_run_queue_core_does_not_import_clipart_result_modules():
    imports = _imports(ROOT / "v3_run_queue.py")
    for module_name in (
        "studio_alpha_qc",
        "studio_bundle_planner",
        "studio_clipart_recipe",
        "studio_export_membership",
        "studio_set_export_ui",
    ):
        assert module_name not in imports


def test_project_state_core_does_not_import_clipart_persistence_modules():
    imports = _imports(ROOT / "v3_project_state.py")
    assert "studio_clipart_recipe" not in imports
    assert "studio_export_membership" not in imports
