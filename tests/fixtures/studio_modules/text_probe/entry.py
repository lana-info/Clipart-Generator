"""Text-only architecture probe for the public Studio Module API."""
from studio_module_api import (
    CapabilityRequirement,
    CommandDeclaration,
    DocumentTypeDeclaration,
    ModuleRegistration,
)

_TEXT_REQUIREMENT = CapabilityRequirement("providers.text", 1)
_text_contract = None


def bind(context):
    global _text_contract
    if hasattr(context, "services"):
        raise ValueError("capability context exposed legacy services")
    _text_contract = context.capabilities.require(_TEXT_REQUIREMENT)


def _normalize(value):
    if _text_contract is None:
        raise RuntimeError("text capability was not bound")
    return _text_contract.normalize(value)


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
        capabilities=(_TEXT_REQUIREMENT,),
    )
