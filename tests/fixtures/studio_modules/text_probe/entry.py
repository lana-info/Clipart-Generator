"""Text-only architecture probe for the public Studio Module API."""
from studio_module_api import (
    CapabilityRequirement,
    CommandDeclaration,
    DocumentTypeDeclaration,
    ModuleRegistration,
)


def _normalize(value):
    return " ".join(str(value).split())


def register(context):
    if hasattr(context, "services"):
        raise ValueError("public module context exposed legacy services")
    return ModuleRegistration(
        context.module_id,
        context.version,
        commands=(CommandDeclaration("normalize", _normalize),),
        document_types=(DocumentTypeDeclaration(
            "note", "application/vnd.vibix.text-probe+json", 1,
        ),),
        capabilities=(CapabilityRequirement("providers.text", 1),),
    )
