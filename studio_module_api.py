"""Stable, versioned declarations authored by Studio modules."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Callable, Mapping


MODULE_API_VERSION = 1
_NAME = re.compile(r"[a-z][a-z0-9_-]{0,63}\Z")
_CAPABILITY_NAME = re.compile(
    r"[a-z][a-z0-9_-]{0,63}(?:\.[a-z][a-z0-9_-]{0,63}){0,7}\Z"
)


class ModuleRuntimeError(RuntimeError):
    """A public module declaration or runtime contract is invalid."""


# Public name for module authors; the legacy class name is retained so existing
# runtime error contracts and diagnostics do not change during extraction.
ModuleApiError = ModuleRuntimeError


def _declaration_name(value: str) -> str:
    if not isinstance(value, str) or not _NAME.fullmatch(value):
        raise ModuleApiError("Invalid module declaration name")
    return value


def _numeric_version(value: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"\d{1,5}\.\d{1,5}\.\d{1,5}", value):
        raise ModuleApiError("Invalid module registration version")
    return value


def _capability_name(value: str) -> str:
    if not isinstance(value, str) or len(value) > 255 or not _CAPABILITY_NAME.fullmatch(value):
        raise ModuleApiError("Invalid capability name")
    return value


@dataclass(frozen=True, slots=True)
class CapabilityRequirement:
    """One exact version of a host capability required by a module."""

    name: str
    version: int

    def __post_init__(self) -> None:
        _capability_name(self.name)
        if type(self.version) is not int or not 1 <= self.version <= 65535:
            raise ModuleApiError("Invalid capability version")

    @property
    def key(self) -> str:
        return f"{self.name}.v{self.version}"


@dataclass(frozen=True, slots=True)
class CommandDeclaration:
    name: str
    handler: Callable[..., Any] = field(repr=False, compare=False)

    def __post_init__(self) -> None:
        _declaration_name(self.name)
        if not callable(self.handler):
            raise ModuleApiError("Command handler must be callable")


@dataclass(frozen=True, slots=True)
class PageDeclaration:
    name: str
    factory: Callable[..., Any] = field(repr=False, compare=False)

    def __post_init__(self) -> None:
        _declaration_name(self.name)
        if not callable(self.factory):
            raise ModuleApiError("Page factory must be callable")


@dataclass(frozen=True, slots=True)
class DocumentTypeDeclaration:
    name: str
    mime_type: str
    schema_version: int

    def __post_init__(self) -> None:
        _declaration_name(self.name)
        if (
            not isinstance(self.mime_type, str)
            or not self.mime_type
            or any(character.isspace() for character in self.mime_type)
            or "/" not in self.mime_type
        ):
            raise ModuleApiError("Document MIME type is invalid")
        if type(self.schema_version) is not int or not 1 <= self.schema_version <= 65535:
            raise ModuleApiError("Document schema version is invalid")


def _frozen_declarations(
    module_id: str,
    values: Any,
    expected: type[Any],
) -> dict[str, Any]:
    if not isinstance(values, (tuple, list)):
        raise ModuleApiError("Module declarations must be a sequence")
    result: dict[str, Any] = {}
    for value in values:
        qualified_name = f"{module_id}.{getattr(value, 'name', '')}"
        if not isinstance(value, expected) or qualified_name in result:
            raise ModuleApiError("Invalid or duplicate module declaration")
        result[qualified_name] = value
    return result


@dataclass(frozen=True, slots=True)
class ModuleRegistration:
    """Version-1 declarations returned by a module's ``register(context)``."""

    module_id: str
    version: str
    pages: tuple[PageDeclaration, ...] = ()
    commands: tuple[CommandDeclaration, ...] = ()
    document_types: tuple[DocumentTypeDeclaration, ...] = ()
    capabilities: tuple[CapabilityRequirement, ...] = ()
    api_version: int = MODULE_API_VERSION
    _pages: Mapping[str, PageDeclaration] = field(init=False, repr=False, compare=False)
    _commands: Mapping[str, CommandDeclaration] = field(init=False, repr=False, compare=False)
    _document_types: Mapping[str, DocumentTypeDeclaration] = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        _declaration_name(self.module_id)
        _numeric_version(self.version)
        if self.api_version != MODULE_API_VERSION or type(self.api_version) is not int:
            raise ModuleApiError("Unsupported module registration API")
        pages = _frozen_declarations(self.module_id, self.pages, PageDeclaration)
        commands = _frozen_declarations(self.module_id, self.commands, CommandDeclaration)
        documents = _frozen_declarations(self.module_id, self.document_types, DocumentTypeDeclaration)
        if not isinstance(self.capabilities, (tuple, list)):
            raise ModuleApiError("Capability requirements must be a sequence")
        capability_names: set[str] = set()
        capabilities: list[CapabilityRequirement] = []
        for requirement in self.capabilities:
            if not isinstance(requirement, CapabilityRequirement) or requirement.name in capability_names:
                raise ModuleApiError("Invalid or duplicate capability requirement")
            capability_names.add(requirement.name)
            capabilities.append(requirement)
        object.__setattr__(self, "pages", tuple(pages.values()))
        object.__setattr__(self, "commands", tuple(commands.values()))
        object.__setattr__(self, "document_types", tuple(documents.values()))
        object.__setattr__(self, "capabilities", tuple(capabilities))
        object.__setattr__(self, "_pages", MappingProxyType(pages))
        object.__setattr__(self, "_commands", MappingProxyType(commands))
        object.__setattr__(self, "_document_types", MappingProxyType(documents))

    @property
    def entitlement_id(self) -> str:
        """The module ID is also the entitlement identifier in API v1."""
        return self.module_id

    @property
    def page_declarations(self) -> Mapping[str, PageDeclaration]:
        return self._pages

    @property
    def command_declarations(self) -> Mapping[str, CommandDeclaration]:
        return self._commands

    @property
    def document_type_declarations(self) -> Mapping[str, DocumentTypeDeclaration]:
        return self._document_types

    def qualified_name(self, name: str) -> str:
        _declaration_name(name)
        return f"{self.module_id}.{name}"


@dataclass(frozen=True, slots=True)
class ModuleContext:
    """Public registration context: identity only until capabilities are bound."""

    module_id: str
    version: str

    def __post_init__(self) -> None:
        _declaration_name(self.module_id)
        _numeric_version(self.version)


ModuleCommand = CommandDeclaration
ModulePage = PageDeclaration
ModuleDocumentType = DocumentTypeDeclaration


__all__ = [
    "MODULE_API_VERSION", "CapabilityRequirement", "CommandDeclaration",
    "DocumentTypeDeclaration", "ModuleApiError", "ModuleCommand", "ModuleContext",
    "ModuleDocumentType", "ModulePage", "ModuleRegistration", "PageDeclaration",
]
