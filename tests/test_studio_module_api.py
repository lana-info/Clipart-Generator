"""Public Studio Module API contracts; no runtime/provider/UI side effects."""
import ast
import base64
import hashlib
import inspect
import json
import tempfile
import zipfile
from collections.abc import Mapping
from pathlib import Path

import pytest

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from studio_module_api import (
    MODULE_API_VERSION,
    CapabilityBinding,
    CapabilityRequirement,
    CommandDeclaration,
    DocumentTypeDeclaration,
    ModuleApiError,
    ModuleCapabilities,
    ModuleCapabilityContext,
    ModuleContext,
    ModuleRegistration,
)
from studio_module_runtime import (
    CapabilityBroker, CapabilityProvider, ModuleAuthorizationError, ModuleRuntimeError, ModuleRuntimeHost,
)
from studio_modules import ModuleStore, canonical_manifest


def test_public_context_exposes_identity_not_legacy_service_locator():
    context = ModuleContext("text-probe", "1.0.0")
    assert context.module_id == "text-probe"
    assert context.version == "1.0.0"
    assert not hasattr(context, "services")
    assert not hasattr(context, "main_window")
    assert not hasattr(context, "worker")


def test_capability_requirement_is_exact_versioned_identifier():
    requirement = CapabilityRequirement("providers.text", 1)
    assert requirement.key == "providers.text.v1"
    for name in ("", "Providers.text", "providers..text", "providers/text", "clipart alpha"):
        with pytest.raises(ModuleApiError):
            CapabilityRequirement(name, 1)
    for version in (True, 0, -1, 65536, "1"):
        with pytest.raises(ModuleApiError):
            CapabilityRequirement("providers.text", version)


def test_registration_is_text_capable_without_ui_or_image_contracts():
    registration = ModuleRegistration(
        "text-probe",
        "1.0.0",
        commands=(CommandDeclaration("summarize", lambda text: text.strip()),),
        document_types=(DocumentTypeDeclaration(
            "note", "application/vnd.vibix.text-probe+json", 1,
        ),),
        capabilities=(CapabilityRequirement("providers.text", 1),),
    )
    assert registration.api_version == MODULE_API_VERSION == 1
    assert registration.entitlement_id == "text-probe"
    assert registration.pages == ()
    assert registration.capabilities[0].key == "providers.text.v1"
    assert registration.document_types[0].name == "note"


def test_registration_rejects_duplicate_capability_names_even_across_versions():
    with pytest.raises(ModuleApiError):
        ModuleRegistration(
            "text-probe",
            "1.0.0",
            capabilities=(
                CapabilityRequirement("providers.text", 1),
                CapabilityRequirement("providers.text", 2),
            ),
        )


def test_public_api_module_has_no_project_local_dependencies():
    import studio_module_api

    source = inspect.getsource(studio_module_api)
    forbidden = (
        "clipart", "pinterest", "processing", "studio_patterns", "PyQt",
        "WorkerThread", "api_credentials", "provider_clients", "v3_",
    )
    assert not any(token in source for token in forbidden)


def test_runtime_reexports_the_same_public_declaration_types():
    import studio_module_runtime as runtime

    assert runtime.ModuleRegistration is ModuleRegistration
    assert runtime.CommandDeclaration is CommandDeclaration
    assert runtime.DocumentTypeDeclaration is DocumentTypeDeclaration
    assert runtime.ModuleContext is ModuleContext
    assert runtime.ModuleRuntimeError is ModuleApiError


FIXTURE = Path(__file__).parent / "fixtures" / "studio_modules" / "text_probe" / "entry.py"


def test_text_probe_fixture_is_text_only_public_api_consumer():
    source = FIXTURE.read_text(encoding="utf-8")
    tree = ast.parse(source)
    project_imports = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            project_imports.update(alias.name.split(".", 1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            project_imports.add(node.module.split(".", 1)[0])
    assert project_imports == {"studio_module_api", "studio_project_api", "studio_provider_api", "studio_job_api"}
    lowered = source.casefold()
    assert "clipart" not in lowered
    assert "image" not in lowered
    assert "pyqt" not in lowered


def _signed_text_probe_package(root: Path, private: Ed25519PrivateKey) -> Path:
    code = FIXTURE.read_bytes()
    manifest = {
        "schema_version": 1,
        "module_id": "text-probe",
        "version": "1.0.0",
        "module_api": 1,
        "studio_min": "3.2.0",
        "studio_max_exclusive": "4.0.0",
        "platforms": ["test"],
        "dependencies": [],
        "entrypoint": "entry.py",
        "files": {"entry.py": hashlib.sha256(code).hexdigest()},
    }
    signature = {
        "key_id": "fixture",
        "signature": base64.b64encode(private.sign(canonical_manifest(manifest))).decode(),
    }
    package = root / "text-probe.zip"
    with zipfile.ZipFile(package, "w") as archive:
        archive.writestr("manifest.json", json.dumps(manifest))
        archive.writestr("signature.json", json.dumps(signature))
        archive.writestr("entry.py", code)
    return package


class _ScopedTextContract:
    def __init__(self, module_id):
        self.module_id = module_id

    def execute(self, request):
        return {"text": f"{self.module_id}:" + " ".join(str(request.input_payload["text"]).split())}


def test_signed_text_probe_negotiates_scoped_public_capabilities():
    with tempfile.TemporaryDirectory() as folder:
        root = Path(folder)
        private = Ed25519PrivateKey.generate()
        store = ModuleStore(
            root / "modules",
            studio_version="3.2.0",
            platform="test",
            trusted_keys={"fixture": private.public_key().public_bytes_raw()},
        )
        store.install(_signed_text_probe_package(root, private))
        denied = ModuleRuntimeHost(store, lambda module_id, _action: module_id == "text-probe")
        with pytest.raises(ModuleRuntimeError, match="providers.text.v1"):
            denied.activate("text-probe", "1.0.0")
        assert denied.registration("text-probe") is None

        authorized_ids = []
        scoped_modules = []
        broker = CapabilityBroker((
            CapabilityProvider(
                CapabilityRequirement("providers.text", 1),
                lambda module_id: scoped_modules.append(module_id) or _ScopedTextContract(module_id),
            ),
            CapabilityProvider(
                CapabilityRequirement("projects", 1),
                lambda module_id: scoped_modules.append(module_id) or object(),
            ),
            CapabilityProvider(
                CapabilityRequirement("jobs", 1),
                lambda module_id: scoped_modules.append(module_id) or object(),
            ),
        ))
        host = ModuleRuntimeHost(
            store,
            lambda module_id, _action: (authorized_ids.append(module_id), 1)[1],
            capability_broker=broker,
        )
        # Authorization must grant literal True; generic truthy values remain denied.
        with pytest.raises(ModuleAuthorizationError):
            host.activate("text-probe", "1.0.0")
        host = ModuleRuntimeHost(
            store,
            lambda module_id, _action: (authorized_ids.append(module_id), True)[1],
            capability_broker=broker,
        )
        info = host.activate("text-probe", "1.0.0")
        assert info.module_id == "text-probe"
        assert [page.name for page in info.pages] == ["home"]
        assert info.document_types[0].mime_type == "application/vnd.vibix.text-probe+json"
        assert host.invoke_command("text-probe", "normalize", "  alpha   beta ") == "text-probe:alpha beta"
        assert scoped_modules == ["text-probe", "text-probe", "text-probe"]
        assert set(authorized_ids) == {"text-probe"}


def test_module_capabilities_are_exact_scoped_objects_not_a_mapping():
    requirement = CapabilityRequirement("providers.text", 1)
    contract = object()
    capabilities = ModuleCapabilities((CapabilityBinding(requirement, contract),))
    context = ModuleCapabilityContext("text-probe", "1.0.0", capabilities)
    assert not isinstance(capabilities, Mapping)
    assert not hasattr(capabilities, "__getitem__")
    assert context.capabilities.require(requirement) is contract
    assert context.capabilities.requirements == (requirement,)
    with pytest.raises(AttributeError):
        capabilities._bindings = ()
    with pytest.raises(ModuleApiError, match="not bound"):
        capabilities.require(CapabilityRequirement("providers.text", 2))
    with pytest.raises(ModuleApiError, match="not bound"):
        capabilities.require(CapabilityRequirement("assets", 1))


def test_capability_broker_scopes_exact_provider_factory_to_module_identity():
    requirement = CapabilityRequirement("providers.text", 1)
    calls = []
    broker = CapabilityBroker((
        CapabilityProvider(requirement, lambda module_id: calls.append(module_id) or {"module": module_id}),
    ))
    capabilities = broker.scope("text-probe", (requirement,))
    assert capabilities.require(requirement) == {"module": "text-probe"}
    assert calls == ["text-probe"]
    with pytest.raises(ModuleRuntimeError, match="providers.text.v2"):
        broker.scope("text-probe", (CapabilityRequirement("providers.text", 2),))


def test_extended_text_probe_uses_only_public_capability_apis_and_optional_page():
    source = FIXTURE.read_text(encoding="utf-8")
    tree = ast.parse(source)
    project_imports = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            project_imports.update(alias.name.split(".", 1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            project_imports.add(node.module.split(".", 1)[0])
    assert project_imports == {
        "studio_module_api", "studio_project_api", "studio_provider_api", "studio_job_api",
    }
    lowered = source.casefold()
    assert "clipart" not in lowered
    assert "image" not in lowered
    assert "pyqt" not in lowered


def test_extended_text_probe_runs_projects_provider_job_and_page_end_to_end():
    from studio_job_services import CoreJobService, JobLauncher
    from studio_project_capability import ScopedProjectCapability
    from studio_project_documents import PreparedProjectDocument, ProjectDocumentService
    from studio_projects import ProjectStore
    from studio_provider_services import CoreProviderFacade, ProtectedProviderExecutor

    class TextAdapter:
        module_id = "text-probe"
        document_type = "note"
        current_version = 1
        def open_state(self, state, version): return dict(state)
        def prepare_save(self, state, source_version):
            return PreparedProjectDocument(1, dict(state))
        def before_save(self, store, existing, prepared): return None

    class TextExecutor(ProtectedProviderExecutor):
        def preflight(self, module_id, request):
            return {"estimated_cost": "0", "currency": "USD"}
        def execute_protected(self, module_id, request, preflight):
            return {"text": f"{module_id}:" + " ".join(request.input_payload["text"].split())}

    with tempfile.TemporaryDirectory() as folder:
        root = Path(folder)
        private = Ed25519PrivateKey.generate()
        store = ModuleStore(
            root / "modules", studio_version="3.2.0", platform="test",
            trusted_keys={"fixture": private.public_key().public_bytes_raw()},
        )
        store.install(_signed_text_probe_package(root, private))
        documents = ProjectDocumentService(ProjectStore(root / "projects"), (TextAdapter(),))
        host_box = {}
        launched = []

        def launch(module_id, request, complete):
            launched.append((module_id, request.operation, dict(request.payload)))
            complete()
            return "job-1"

        broker = CapabilityBroker((
            CapabilityProvider(
                CapabilityRequirement("projects", 1),
                lambda module_id: ScopedProjectCapability(module_id, documents),
            ),
            CapabilityProvider(
                CapabilityRequirement("providers.text", 1),
                lambda module_id: CoreProviderFacade(
                    module_id, "text", TextExecutor(), lambda *_args: True,
                ),
            ),
            CapabilityProvider(
                CapabilityRequirement("jobs", 1),
                lambda module_id: CoreJobService(
                    module_id, host_box["host"], (JobLauncher("normalize_job", launch),),
                ),
            ),
        ))
        host = ModuleRuntimeHost(store, lambda _module, _action: True, capability_broker=broker)
        host_box["host"] = host
        info = host.activate("text-probe", "1.0.0")
        assert [page.name for page in info.pages] == ["home"]
        page = host.create_page("text-probe", "home")
        assert page.value == "text-probe.home"
        page.close()

        project_id = host.invoke_command("text-probe", "create_note", "Note", "hello")
        assert host.invoke_command("text-probe", "read_note", project_id) == "hello"
        assert host.invoke_command("text-probe", "normalize", "  alpha   beta ") == "text-probe:alpha beta"
        assert host.invoke_command("text-probe", "run_job", "queued") == "job-1"
        assert launched == [("text-probe", "normalize_job", {"text": "queued"})]
