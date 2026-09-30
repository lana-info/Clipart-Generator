"""Signed Prompt Composer entrypoint. Installed only inside a verified package."""
from types import SimpleNamespace

from studio_module_api import CommandDeclaration, ModuleRegistration, PageDeclaration


def kernel():
    from .prompt_composer import catalog, engine, model

    return SimpleNamespace(
        catalogue=catalog.catalogue,
        new_draft=model.new_draft,
        validate_draft=model.validate_draft,
        rendered_text=model.rendered_text,
        generate_variants=engine.generate_variants,
        preflight_ai=engine.preflight_ai,
        validate_single_scene=engine.validate_single_scene,
        FIELD_KEYS=model.FIELD_KEYS,
    )


def create_page(host):
    from .prompt_composer.ui import PromptComposerPage

    return PromptComposerPage(host)


def register(context):
    return ModuleRegistration(
        context.module_id, context.version,
        pages=(PageDeclaration('main', create_page),),
        commands=(CommandDeclaration('kernel', kernel),),
    )
