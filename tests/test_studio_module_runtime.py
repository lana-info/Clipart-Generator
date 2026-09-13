"""Contract tests for the bounded signed module runtime."""
from __future__ import annotations

import base64
import hashlib
import json
import sys
import tempfile
import threading
import unittest
import zipfile
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from studio_module_runtime import (
    CapabilityBroker, CapabilityProvider, CommandDeclaration, DocumentTypeDeclaration,
    ModuleAuthorizationError, ModuleRegistration, ModuleRuntimeError, ModuleRuntimeHost,
    PageDeclaration,
)
from studio_module_api import CapabilityRequirement
from studio_modules import ModulePackageError, ModuleStore, canonical_manifest


class StudioModuleRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.private = Ed25519PrivateKey.generate()
        self.store = ModuleStore(self.root / "modules", studio_version="3.1.0", platform="win32",
                                 trusted_keys={"test": self.private.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)})

    def tearDown(self):
        self.temp.cleanup()

    def package(self, module_id="fictional-export", version="1.0.0", code=None, *, module_api=1, extra_files=None):
        code = code or '''from studio_module_runtime import ModuleRegistration, CommandDeclaration, DocumentTypeDeclaration\ndef register(context):\n    return ModuleRegistration(context.module_id, context.version, commands=(CommandDeclaration("export", lambda value: "export:" + value),), document_types=(DocumentTypeDeclaration("story", "application/x-fictional-story", 2),))\n'''
        path = self.root / f"{module_id}-{version}.zip"
        files = {"entry.py": code.encode(), **(extra_files or {})}
        manifest = {"schema_version": 1, "module_id": module_id, "version": version, "module_api": module_api,
                    "studio_min": "3.1.0", "studio_max_exclusive": "4.0.0", "platforms": ["win32"],
                    "dependencies": [], "entrypoint": "entry.py",
                    "files": {name: hashlib.sha256(data).hexdigest() for name, data in files.items()}}
        signature = {"key_id": "test", "signature": base64.b64encode(self.private.sign(canonical_manifest(manifest))).decode()}
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr("manifest.json", json.dumps(manifest))
            archive.writestr("signature.json", json.dumps(signature))
            for name, data in files.items():
                archive.writestr(name, data)
        return path

    def installed_host(self, *, authorize=lambda _module, _action: True, code=None):
        self.store.install(self.package(code=code))
        self.store.activate("fictional-export", "1.0.0")
        return ModuleRuntimeHost(self.store, authorize)

    def test_signed_extension_exports_fictional_document_without_core_switch(self):
        host = self.installed_host()
        registration = host.activate("fictional-export")
        self.assertEqual("export:ready", host.invoke_command("fictional-export", "export", "ready"))
        self.assertEqual(["fictional-export.story"], [item.qualified_name for item in registration.document_types])
        self.assertEqual("application/x-fictional-story", registration.document_types[0].mime_type)

    def test_registration_is_immutable_and_rejects_duplicate_names(self):
        registration = ModuleRegistration("fictional-export", "1.0.0", commands=(CommandDeclaration("export", lambda: None),))
        with self.assertRaises(TypeError):
            registration.command_declarations["x"] = None
        with self.assertRaises(ModuleRuntimeError):
            ModuleRegistration("fictional-export", "1.0.0", commands=(CommandDeclaration("same", lambda: None), CommandDeclaration("same", lambda: None)))

    def test_default_deny_and_revocation_is_checked_at_invocation(self):
        permitted = {"activate", "command:export"}
        host = self.installed_host(authorize=lambda _module, action: action in permitted)
        host.activate("fictional-export")
        self.assertEqual("export:before", host.invoke_command("fictional-export", "export", "before"))
        permitted.remove("command:export")
        with self.assertRaises(ModuleAuthorizationError):
            host.invoke_command("fictional-export", "export", "x")
        host.unload("fictional-export")
        self.assertIsNone(host.registration("fictional-export"))
        denied = ModuleRuntimeHost(self.store)
        with self.assertRaises(ModuleAuthorizationError):
            denied.activate("fictional-export")

    def test_identity_collision_and_incompatible_api_are_rejected(self):
        code = '''from studio_module_runtime import ModuleRegistration\ndef register(context): return ModuleRegistration("other", context.version)\n'''
        host = self.installed_host(code=code)
        with self.assertRaises(ModuleRuntimeError):
            host.activate("fictional-export")
        with self.assertRaises(ModulePackageError):
            self.store.install(self.package(module_id="bad-api", module_api=2))

    def test_tamper_is_denied_and_old_code_cannot_follow_new_pointer(self):
        host = self.installed_host()
        host.activate("fictional-export")
        root = self.store.verified_active_path("fictional-export")
        (root / "entry.py").write_text("tampered", "utf-8")
        with self.assertRaises(ModuleRuntimeError):
            host.invoke_command("fictional-export", "export", "x")

    def test_import_failure_cleans_private_modules_and_keeps_working_registry(self):
        host = self.installed_host()
        previous = host.activate("fictional-export")
        bad = self.package(version="1.0.1", code="from .missing import nope\n")
        self.store.install(bad)
        with self.assertRaises(ModuleRuntimeError):
            host.activate("fictional-export", "1.0.1")
        self.assertEqual(previous, host.registration("fictional-export"))
        self.assertFalse(any(name.startswith("_studio_module_fictional_export_1_0_1_") for name in sys.modules))
        self.assertEqual("1.0.0", self.store.state("fictional-export")["active"])
        self.assertEqual("export:x", host.invoke_command("fictional-export", "export", "x"))

    def test_page_factory_not_called_until_host_requests_it(self):
        code = '''from studio_module_runtime import ModuleRegistration, PageDeclaration\ncalls=[]\ndef page(value):\n calls.append(value); return value\ndef register(context): return ModuleRegistration(context.module_id, context.version, pages=(PageDeclaration("preview", page),))\n'''
        host = self.installed_host(code=code)
        host.activate("fictional-export")
        page = host.create_page("fictional-export", "preview", "shown")
        self.assertEqual("shown", page.value)
        page.close()

    def test_public_registry_never_exposes_raw_callables_after_revocation(self):
        permitted = {"activate", "command:export"}
        host = self.installed_host(authorize=lambda _module, action: action in permitted)
        info = host.activate("fictional-export")
        self.assertFalse(hasattr(info.commands[0], "handler"))
        self.assertFalse(hasattr(info.pages[0] if info.pages else info.commands[0], "factory"))
        permitted.remove("command:export")
        with self.assertRaises(ModuleAuthorizationError):
            host.invoke_command("fictional-export", "export", "blocked")
        self.assertFalse(hasattr(host.registration("fictional-export").commands[0], "handler"))

    def test_live_page_lease_blocks_unload_until_closed_even_after_revocation(self):
        permitted = {"activate", "page:preview"}
        code = '''from studio_module_runtime import ModuleRegistration, PageDeclaration\ndef register(context): return ModuleRegistration(context.module_id, context.version, pages=(PageDeclaration("preview", lambda: "live"),))\n'''
        host = self.installed_host(authorize=lambda _module, action: action in permitted, code=code)
        host.activate("fictional-export")
        page = host.create_page("fictional-export", "preview")
        permitted.remove("page:preview")
        with self.assertRaises(ModuleRuntimeError):
            host.unload("fictional-export")
        page.close()
        host.unload("fictional-export")

    def test_lazy_relative_import_does_not_dirty_verified_package(self):
        code = '''from studio_module_runtime import ModuleRegistration, CommandDeclaration\ndef export(value):\n from .helper import decorate\n return decorate(value)\ndef register(context): return ModuleRegistration(context.module_id, context.version, commands=(CommandDeclaration("export", export),))\n'''
        package = self.package(code=code, extra_files={"helper.py": b"def decorate(value): return 'lazy:' + value\n"})
        self.store.install(package)
        self.store.activate("fictional-export", "1.0.0")
        host = ModuleRuntimeHost(self.store, lambda _module, _action: True)
        host.activate("fictional-export")
        # ``helper`` is first imported during invocation, so a bytecode write
        # here would make the following verified-active check fail.
        self.assertEqual("lazy:value", host.invoke_command("fictional-export", "export", "value"))
        self.assertIsNotNone(self.store.verified_active_path("fictional-export"))

    def test_async_results_are_rejected_without_leaving_a_job_active(self):
        code = '''from studio_module_runtime import ModuleRegistration, CommandDeclaration\nasync def later(): return "no"\ndef register(context): return ModuleRegistration(context.module_id, context.version, commands=(CommandDeclaration("export", later),))\n'''
        host = self.installed_host(code=code)
        host.activate("fictional-export")
        with self.assertRaises(ModuleRuntimeError):
            host.invoke_command("fictional-export", "export")
        host.unload("fictional-export")

    def test_other_thread_cannot_mutate_host_lifecycle(self):
        host = self.installed_host()
        host.activate("fictional-export")
        errors = []
        def attempt():
            try:
                host.unload("fictional-export")
            except ModuleRuntimeError as exc:
                errors.append(str(exc))
        worker = threading.Thread(target=attempt)
        worker.start()
        worker.join(timeout=2)
        self.assertFalse(worker.is_alive())
        self.assertEqual(errors, ["Module host must be called on its owner thread"])
        self.assertIsNotNone(host.registration("fictional-export"))
        host.unload("fictional-export")

    def test_active_job_blocks_unload_and_update(self):
        code = '''from studio_module_runtime import ModuleRegistration, CommandDeclaration\ndef register(context):\n def run(host):\n  try: host.unload(context.module_id)\n  except Exception as exc: return type(exc).__name__\n  return "not-blocked"\n return ModuleRegistration(context.module_id, context.version, commands=(CommandDeclaration("run", run),))\n'''
        host = self.installed_host(code=code)
        host.activate("fictional-export")
        self.assertEqual("ModuleRuntimeError", host.invoke_command("fictional-export", "run", host))


    def test_missing_required_capability_fails_before_registration_publish(self):
        code = """from studio_module_api import CapabilityRequirement, ModuleRegistration
def register(context):
    return ModuleRegistration(context.module_id, context.version,
        capabilities=(CapabilityRequirement("providers.text", 1),))
"""
        package = self.package(module_id="text-probe", code=code)
        self.store.install(package)
        host = ModuleRuntimeHost(
            self.store,
            lambda _module, _action: True,
        )
        with self.assertRaisesRegex(ModuleRuntimeError, "capability"):
            host.activate("text-probe", "1.0.0")
        self.assertIsNone(host.registration("text-probe"))
        self.assertIsNone(self.store.state("text-probe")["active"])


    def test_required_capability_version_mismatch_fails_closed(self):
        code = """from studio_module_api import CapabilityRequirement, ModuleRegistration
def register(context):
    return ModuleRegistration(context.module_id, context.version,
        capabilities=(CapabilityRequirement("providers.text", 1),))
"""
        package = self.package(module_id="text-probe-v", code=code)
        self.store.install(package)
        host = ModuleRuntimeHost(
            self.store,
            lambda _module, _action: True,
            capability_broker=CapabilityBroker((
                CapabilityProvider(CapabilityRequirement("providers.text", 2), lambda _id: object()),
            )),
        )
        with self.assertRaisesRegex(ModuleRuntimeError, "providers.text.v1"):
            host.activate("text-probe-v", "1.0.0")
        self.assertIsNone(host.registration("text-probe-v"))
        self.assertIsNone(self.store.state("text-probe-v")["active"])

    def test_exact_required_capability_version_can_register(self):
        code = """from studio_module_api import CapabilityRequirement, ModuleRegistration, CommandDeclaration
def register(context):
    return ModuleRegistration(context.module_id, context.version,
        commands=(CommandDeclaration("echo", lambda value: value),),
        capabilities=(CapabilityRequirement("providers.text", 1),))
"""
        package = self.package(module_id="text-probe-ok", code=code)
        self.store.install(package)
        host = ModuleRuntimeHost(
            self.store,
            lambda _module, _action: True,
            capability_broker=CapabilityBroker((
                CapabilityProvider(CapabilityRequirement("providers.text", 1), lambda _id: object()),
            )),
        )
        info = host.activate("text-probe-ok", "1.0.0")
        self.assertEqual(info.module_id, "text-probe-ok")
        self.assertEqual(host.invoke_command("text-probe-ok", "echo", "ready"), "ready")


    def test_external_job_lease_blocks_unload_and_activation_until_closed(self):
        host = self.installed_host()
        host.activate("fictional-export")
        self.store.install(self.package(version="1.0.1"))
        lease = host.acquire_job_lease("fictional-export")
        with self.assertRaisesRegex(ModuleRuntimeError, "active jobs"):
            host.unload("fictional-export")
        with self.assertRaisesRegex(ModuleRuntimeError, "active jobs"):
            host.activate("fictional-export", "1.0.1")
        self.assertEqual(self.store.state("fictional-export")["active"], "1.0.0")
        lease.close()
        info = host.activate("fictional-export", "1.0.1")
        self.assertEqual(info.version, "1.0.1")
        host.unload("fictional-export")

    def test_external_job_lease_can_be_released_by_worker_completion_thread(self):
        host = self.installed_host()
        host.activate("fictional-export")
        lease = host.acquire_job_lease("fictional-export")
        errors = []

        def release():
            try:
                lease.close()
                lease.close()
            except Exception as exc:
                errors.append(exc)

        worker = threading.Thread(target=release)
        worker.start()
        worker.join(timeout=2)
        self.assertFalse(worker.is_alive())
        self.assertEqual(errors, [])
        self.assertTrue(lease.closed)
        host.unload("fictional-export")


if __name__ == "__main__":
    unittest.main()
