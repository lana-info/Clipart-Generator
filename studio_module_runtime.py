"""Small, fail-closed runtime for already verified Studio module packages.

This is an integration boundary, not a security sandbox.  ``ModuleStore``
verifies the package on disk; this module verifies it again at each transition
where an old in-memory module could otherwise outlive an activation change.
"""
from __future__ import annotations

import importlib.util
import inspect
import json
import re
import sys
import threading
import types
import uuid
from concurrent.futures import Future
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import Any, Callable, Mapping

from studio_modules import ModulePackageError, ModuleStore

MODULE_API_VERSION = 1
_BYTECODE_EXECUTION_LOCK = threading.RLock()
_NAME = re.compile(r"[a-z][a-z0-9_-]{0,63}\Z")


class ModuleRuntimeError(RuntimeError):
    """A module could not be loaded, published, or invoked safely."""


class ModuleAuthorizationError(ModuleRuntimeError):
    """The trusted host did not explicitly grant an operation."""


@dataclass(frozen=True, slots=True)
class CommandDeclaration:
    """A trusted host-only executable declaration; do not expose handlers to UI code."""
    name: str
    handler: Callable[..., Any] = field(repr=False, compare=False)

    def __post_init__(self) -> None:
        _declaration_name(self.name)
        if not callable(self.handler):
            raise ModuleRuntimeError("Command handler must be callable")


@dataclass(frozen=True, slots=True)
class PageDeclaration:
    """A trusted host-only executable declaration; do not expose factories to UI code."""
    name: str
    factory: Callable[..., Any] = field(repr=False, compare=False)

    def __post_init__(self) -> None:
        _declaration_name(self.name)
        if not callable(self.factory):
            raise ModuleRuntimeError("Page factory must be callable")


@dataclass(frozen=True, slots=True)
class DocumentTypeDeclaration:
    name: str
    mime_type: str
    schema_version: int

    def __post_init__(self) -> None:
        _declaration_name(self.name)
        if (not isinstance(self.mime_type, str) or not self.mime_type or
                any(c.isspace() for c in self.mime_type) or "/" not in self.mime_type):
            raise ModuleRuntimeError("Document MIME type is invalid")
        if type(self.schema_version) is not int or not 1 <= self.schema_version <= 65535:
            raise ModuleRuntimeError("Document schema version is invalid")


@dataclass(frozen=True, slots=True)
class ModuleRegistration:
    """Version-1 declarative registration returned by ``register(context)``.

    The host never calls command handlers or page factories while registering.
    Their qualified names are ``<module_id>.<name>`` and are exposed through
    the immutable declaration mappings.
    """

    module_id: str
    version: str
    pages: tuple[PageDeclaration, ...] = ()
    commands: tuple[CommandDeclaration, ...] = ()
    document_types: tuple[DocumentTypeDeclaration, ...] = ()
    api_version: int = MODULE_API_VERSION
    _pages: Mapping[str, PageDeclaration] = field(init=False, repr=False, compare=False)
    _commands: Mapping[str, CommandDeclaration] = field(init=False, repr=False, compare=False)
    _document_types: Mapping[str, DocumentTypeDeclaration] = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        _declaration_name(self.module_id)
        _numeric_version(self.version)
        if self.api_version != MODULE_API_VERSION or type(self.api_version) is not int:
            raise ModuleRuntimeError("Unsupported module registration API")
        pages = _frozen_declarations(self.module_id, self.pages, PageDeclaration)
        commands = _frozen_declarations(self.module_id, self.commands, CommandDeclaration)
        documents = _frozen_declarations(self.module_id, self.document_types, DocumentTypeDeclaration)
        object.__setattr__(self, "pages", tuple(pages.values()))
        object.__setattr__(self, "commands", tuple(commands.values()))
        object.__setattr__(self, "document_types", tuple(documents.values()))
        object.__setattr__(self, "_pages", MappingProxyType(pages))
        object.__setattr__(self, "_commands", MappingProxyType(commands))
        object.__setattr__(self, "_document_types", MappingProxyType(documents))

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
    module_id: str
    version: str
    services: Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class CommandInfo:
    name: str
    qualified_name: str


@dataclass(frozen=True, slots=True)
class PageInfo:
    name: str
    qualified_name: str


@dataclass(frozen=True, slots=True)
class DocumentTypeInfo:
    name: str
    qualified_name: str
    mime_type: str
    schema_version: int


@dataclass(frozen=True, slots=True)
class ModuleInfo:
    """Public metadata only.  It intentionally contains no executable code."""
    module_id: str
    version: str
    pages: tuple[PageInfo, ...]
    commands: tuple[CommandInfo, ...]
    document_types: tuple[DocumentTypeInfo, ...]


class PageHandle:
    """Host-owned lease for a live page value returned by a trusted factory."""

    __slots__ = ("module_id", "name", "value", "_release", "_closed")

    def __init__(self, module_id: str, name: str, value: Any, release: Callable[[], None]):
        self.module_id, self.name, self.value = module_id, name, value
        self._release, self._closed = release, False

    @property
    def closed(self) -> bool:
        return self._closed

    def close(self) -> None:
        if not self._closed:
            self._release()
            self._closed = True


@dataclass(slots=True)
class _LoadedModule:
    registration: ModuleRegistration
    root: Path
    namespace: str


class ModuleRuntimeHost:
    """Owns module imports and the atomically published runtime registry.

    ``authorize(module_id, action)`` is trusted application policy.  Only a
    literal ``True`` grants access.  Actions are ``activate``, ``load``,
    ``command:<name>``, and ``page:<name>``.  Unloading only releases an
    already loaded module, so it remains available after a right is revoked.
    """

    def __init__(self, store: ModuleStore, authorize: Callable[[str, str], bool] | None = None,
                 *, services: Mapping[str, Any] | None = None):
        if not isinstance(store, ModuleStore):
            raise TypeError("store must be a ModuleStore")
        if authorize is not None and not callable(authorize):
            raise TypeError("authorize must be callable")
        self.store = store
        self._authorize_callback = authorize
        self._services = MappingProxyType(dict(services or {}))
        self._loaded: dict[str, _LoadedModule] = {}
        self._active_jobs: dict[str, int] = {}
        self._page_leases: dict[str, set[str]] = {}
        # The host executes package callbacks on one serialized host path.  It
        # is not an OS sandbox: package code has the application's Python
        # privileges and must be from a verified, authorized publisher.
        self._execution_lock = _BYTECODE_EXECUTION_LOCK
        self._owner_thread = threading.get_ident()

    @property
    def registrations(self) -> Mapping[str, ModuleInfo]:
        self._assert_owner_thread()
        return MappingProxyType({module_id: _module_info(item.registration) for module_id, item in self._loaded.items()})

    def registration(self, module_id: str) -> ModuleInfo | None:
        self._assert_owner_thread()
        loaded = self._loaded.get(module_id)
        return _module_info(loaded.registration) if loaded is not None else None

    def activate(self, module_id: str, version: str | None = None) -> ModuleInfo:
        """Authorize activation, optionally change the store pointer, then load."""
        self._allowed(module_id, "activate")
        self._ensure_idle(module_id)
        if version is not None:
            previous_state = self.store.state(module_id)
            self.store.activate(module_id, version, busy=False)
            try:
                return _module_info(self._load_verified(module_id))
            except Exception:
                # ModuleStore intentionally exposes no mutating pointer restore
                # API.  Its own atomic writer preserves the complete prior state
                # (including disabled state and rollback target) here.
                self.store._write_state(module_id, previous_state)
                raise
        return _module_info(self._load_verified(module_id))

    def load_active(self, module_id: str) -> ModuleInfo:
        self._allowed(module_id, "load")
        self._ensure_idle(module_id)
        return _module_info(self._load_verified(module_id))

    def unload(self, module_id: str) -> None:
        self._assert_owner_thread()
        self._ensure_idle(module_id)
        loaded = self._loaded.pop(module_id, None)
        if loaded is not None:
            self._purge_namespace(loaded.namespace)

    def invoke_command(self, module_id: str, name: str, *args: Any, **kwargs: Any) -> Any:
        self._allowed(module_id, f"command:{name}")
        loaded = self._current_loaded(module_id)
        try:
            command = loaded.registration.command_declarations[loaded.registration.qualified_name(name)]
        except KeyError as exc:
            raise ModuleRuntimeError("Unknown module command") from exc
        self._active_jobs[module_id] = self._active_jobs.get(module_id, 0) + 1
        try:
            with self._module_execution():
                result = command.handler(*args, **kwargs)
            return self._synchronous_result(result)
        finally:
            remaining = self._active_jobs[module_id] - 1
            if remaining:
                self._active_jobs[module_id] = remaining
            else:
                self._active_jobs.pop(module_id, None)

    def create_page(self, module_id: str, name: str, *args: Any, **kwargs: Any) -> PageHandle:
        self._allowed(module_id, f"page:{name}")
        loaded = self._current_loaded(module_id)
        try:
            factory = loaded.registration.page_declarations[loaded.registration.qualified_name(name)].factory
        except KeyError as exc:
            raise ModuleRuntimeError("Unknown module page") from exc
        self._active_jobs[module_id] = self._active_jobs.get(module_id, 0) + 1
        try:
            with self._module_execution():
                result = factory(*args, **kwargs)
            value = self._synchronous_result(result)
            token = uuid.uuid4().hex
            self._page_leases.setdefault(module_id, set()).add(token)
            return PageHandle(module_id, name, value, lambda: self._release_page(module_id, token))
        finally:
            remaining = self._active_jobs[module_id] - 1
            if remaining:
                self._active_jobs[module_id] = remaining
            else:
                self._active_jobs.pop(module_id, None)

    def _load_verified(self, module_id: str) -> ModuleRegistration:
        root, manifest = self._verified_identity(module_id)
        old = self._loaded.get(module_id)
        if old is not None and old.root == root and old.registration.version == manifest["version"]:
            return old.registration
        namespace = "_studio_module_{}_{}_{}".format(
            module_id.replace("-", "_"), manifest["version"].replace(".", "_"), uuid.uuid4().hex)
        try:
            registration = self._import_registration(root, manifest, namespace)
            # Close the verified-to-import race before publishing this registration.
            current_root, current_manifest = self._verified_identity(module_id)
            if current_root != root or current_manifest["version"] != manifest["version"]:
                raise ModuleRuntimeError("Module activation changed while loading")
        except Exception as exc:
            self._purge_namespace(namespace)
            if isinstance(exc, ModuleRuntimeError):
                raise
            raise ModuleRuntimeError("Module registration failed") from exc
        candidate = _LoadedModule(registration, root, namespace)
        # Publish only after all registration validation succeeds.
        self._loaded[module_id] = candidate
        if old is not None:
            self._purge_namespace(old.namespace)
        return registration

    def _import_registration(self, root: Path, manifest: Mapping[str, Any], namespace: str) -> ModuleRegistration:
        entrypoint = root / str(manifest["entrypoint"])
        try:
            entrypoint.relative_to(root)
        except ValueError as exc:
            raise ModuleRuntimeError("Unsafe module entrypoint") from exc
        if not entrypoint.is_file():
            raise ModuleRuntimeError("Module entrypoint is missing")
        spec = importlib.util.spec_from_file_location(namespace, entrypoint,
                                                       submodule_search_locations=[str(root)])
        if spec is None or spec.loader is None:
            raise ModuleRuntimeError("Module entrypoint cannot be loaded")
        module = importlib.util.module_from_spec(spec)
        sys.modules[namespace] = module
        # Keep bytecode disabled through register(), not merely exec_module():
        # a registration may legitimately perform a lazy relative import.
        with self._module_execution():
            spec.loader.exec_module(module)
            register = getattr(module, "register", None)
            if not callable(register):
                raise ModuleRuntimeError("Module entrypoint must export register(context)")
            registration = register(ModuleContext(manifest["module_id"], manifest["version"], self._services))
        if not isinstance(registration, ModuleRegistration):
            raise ModuleRuntimeError("register(context) must return ModuleRegistration")
        if (registration.module_id != manifest["module_id"] or registration.version != manifest["version"]):
            raise ModuleRuntimeError("Module registration identity mismatch")
        return registration

    def _current_loaded(self, module_id: str) -> _LoadedModule:
        loaded = self._loaded.get(module_id)
        if loaded is None:
            raise ModuleRuntimeError("Module is not loaded")
        root, manifest = self._verified_identity(module_id)
        if root != loaded.root or manifest["version"] != loaded.registration.version:
            self._loaded.pop(module_id, None)
            self._purge_namespace(loaded.namespace)
            raise ModuleRuntimeError("Loaded module is no longer the active verified package")
        return loaded

    def _verified_identity(self, module_id: str) -> tuple[Path, Mapping[str, Any]]:
        try:
            root = self.store.verified_active_path(module_id)
        except ModulePackageError as exc:
            raise ModuleRuntimeError("Active module package is not verified") from exc
        if root is None:
            raise ModuleRuntimeError("Module is not active")
        # verified_active_path() is deliberately called first.  Manifest data is
        # never used as a license/authorization claim; it only pins code identity.
        manifest_path = root / "manifest.json"
        try:
            manifest = json.loads(manifest_path.read_text("utf-8"))
        except (OSError, ValueError) as exc:
            raise ModuleRuntimeError("Verified module manifest cannot be read") from exc
        if (not isinstance(manifest, dict) or manifest.get("module_id") != module_id or
                not isinstance(manifest.get("version"), str) or manifest.get("module_api") != MODULE_API_VERSION):
            raise ModuleRuntimeError("Verified module manifest identity is invalid")
        return root.resolve(), MappingProxyType(manifest)

    def _allowed(self, module_id: str, action: str) -> None:
        self._assert_owner_thread()
        if self._authorize_callback is None or self._authorize_callback(module_id, action) is not True:
            raise ModuleAuthorizationError("Module operation is not authorized")

    def _assert_owner_thread(self) -> None:
        if threading.get_ident() != self._owner_thread:
            raise ModuleRuntimeError("Module host must be called on its owner thread")

    def _ensure_idle(self, module_id: str) -> None:
        if self._active_jobs.get(module_id, 0) or self._page_leases.get(module_id):
            raise ModuleRuntimeError("Module has active jobs or live pages")

    def _release_page(self, module_id: str, token: str) -> None:
        self._assert_owner_thread()
        leases = self._page_leases.get(module_id)
        if leases is not None:
            leases.discard(token)
            if not leases:
                self._page_leases.pop(module_id, None)

    @contextmanager
    def _module_execution(self):
        """Serialize synchronous package code and preserve verified inventory.

        ``sys.dont_write_bytecode`` is process-global.  The lock serializes all
        host callbacks while it is set; callers must route official module work
        through this host rather than run it concurrently themselves.
        """
        with self._execution_lock:
            previous = sys.dont_write_bytecode
            try:
                sys.dont_write_bytecode = True
                yield
            finally:
                sys.dont_write_bytecode = previous

    @staticmethod
    def _synchronous_result(value: Any) -> Any:
        """v1 has no job lease protocol, so asynchronous work is not accepted."""
        if inspect.isawaitable(value) or inspect.isgenerator(value) or isinstance(value, Future):
            close = getattr(value, "close", None)
            if callable(close):
                close()
            cancel = getattr(value, "cancel", None)
            if callable(cancel):
                cancel()
            raise ModuleRuntimeError("Module v1 commands and pages must finish synchronously")
        return value

    @staticmethod
    def _purge_namespace(namespace: str) -> None:
        for key in [key for key in sys.modules if key == namespace or key.startswith(namespace + ".")]:
            sys.modules.pop(key, None)


def _declaration_name(value: str) -> str:
    if not isinstance(value, str) or not _NAME.fullmatch(value):
        raise ModuleRuntimeError("Invalid module declaration name")
    return value


def _numeric_version(value: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"\d{1,5}\.\d{1,5}\.\d{1,5}", value):
        raise ModuleRuntimeError("Invalid module registration version")
    return value


def _frozen_declarations(module_id: str, values: Any, expected: type[Any]) -> dict[str, Any]:
    if not isinstance(values, (tuple, list)):
        raise ModuleRuntimeError("Module declarations must be a sequence")
    result: dict[str, Any] = {}
    for value in values:
        qualified_name = f"{module_id}.{getattr(value, 'name', '')}"
        if not isinstance(value, expected) or qualified_name in result:
            raise ModuleRuntimeError("Invalid or duplicate module declaration")
        result[qualified_name] = value
    return result


# Short aliases make the public v1 contract convenient without adding a second
# representation for declarations.
ModuleCommand = CommandDeclaration
ModulePage = PageDeclaration
ModuleDocumentType = DocumentTypeDeclaration


def _module_info(registration: ModuleRegistration) -> ModuleInfo:
    return ModuleInfo(
        registration.module_id,
        registration.version,
        tuple(PageInfo(item.name, registration.qualified_name(item.name)) for item in registration.pages),
        tuple(CommandInfo(item.name, registration.qualified_name(item.name)) for item in registration.commands),
        tuple(DocumentTypeInfo(item.name, registration.qualified_name(item.name), item.mime_type, item.schema_version)
              for item in registration.document_types),
    )
