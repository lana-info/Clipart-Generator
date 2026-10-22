"""Signed Patterns entrypoint. Installed only inside a verified package.

The package payload is ``entry.py`` (this file), ``studio_patterns.py`` and
``studio_patterns_tools.py`` (see ``studio_patterns_package``).  Core never
imports the engine; it reaches it only through the ``kernel`` command.  No page
is declared yet: the Patterns screens arrive with the UI stage, and this module
must not be published to customers before then.
"""
from importlib import import_module
from types import SimpleNamespace

from studio_module_api import CommandDeclaration, DocumentTypeDeclaration, ModuleRegistration

PROJECT_MIME = "application/vnd.vibix.patterns-project+json"
# Stored in every project so a later release can reproduce older layouts.
ALGORITHM_VERSION = 1


def kernel():
    scene = import_module(".studio_patterns", __package__)
    tools = import_module(".studio_patterns_tools", __package__)
    return SimpleNamespace(
        ALGORITHM_VERSION=ALGORITHM_VERSION,
        MAX_DIMENSION=scene.MAX_DIMENSION, MAX_ASSET_PIXELS=scene.MAX_ASSET_PIXELS,
        MAX_JSON_BYTES=scene.MAX_JSON_BYTES,
        AssetRef=scene.AssetRef, PatternElement=scene.PatternElement, PatternScene=scene.PatternScene,
        PatternValidationError=scene.PatternValidationError, RepeatMode=scene.RepeatMode,
        render_supertile=scene.render_supertile, render_preview=scene.render_preview,
        supertile_size=scene.supertile_size, rebuild_layout=scene.rebuild_layout,
        SeamStatus=tools.SeamStatus, layout_scene=tools.layout_scene, wrap_resize=tools.wrap_resize,
        seam_report=tools.seam_report, make_seamless=tools.make_seamless, mirror_tile=tools.mirror_tile,
        tile_preview=tools.tile_preview, export_tile=tools.export_tile,
        inches_to_px=tools.inches_to_px, cm_to_px=tools.cm_to_px,
        encoded_size_hint=tools.encoded_size_hint,
    )


def register(context):
    return ModuleRegistration(
        context.module_id, context.version,
        commands=(CommandDeclaration("kernel", kernel),),
        document_types=(DocumentTypeDeclaration("project", PROJECT_MIME, 1),),
    )
