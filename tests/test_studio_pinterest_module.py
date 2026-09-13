"""Signed-package adapter contract; no Qt pages, network or provider calls."""
import ast
import base64
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock
import zipfile

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from studio_modules import ModuleStore, canonical_manifest
from studio_module_runtime import ModuleRuntimeHost, ModuleAuthorizationError
from workflow_definitions import workflow_for_mode


class PinterestModuleTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        key = Ed25519PrivateKey.generate()
        self.store = ModuleStore(root / "modules", studio_version="3.2.0", platform="test",
            trusted_keys={"fixture": key.public_key().public_bytes_raw()})
        code = (Path(__file__).resolve().parents[1] / "studio_official_modules/pinterest/entry.py").read_bytes()
        manifest = dict(schema_version=1, module_id="pinterest", version="1.0.0", module_api=1,
            studio_min="3.2.0", studio_max_exclusive="4.0.0", platforms=["test"],
            entrypoint="entry.py", files={"entry.py": hashlib.sha256(code).hexdigest()})
        signature = dict(key_id="fixture", signature=base64.b64encode(key.sign(canonical_manifest(manifest))).decode())
        package = root / "pinterest.zip"
        with zipfile.ZipFile(package, "w") as archive:
            archive.writestr("manifest.json", json.dumps(manifest))
            archive.writestr("signature.json", json.dumps(signature))
            archive.writestr("entry.py", code)
        self.store.install(package)

    def test_official_adapter_imports_only_public_module_contract(self):
        path = Path(__file__).resolve().parents[1] / "studio_official_modules/pinterest/entry.py"
        tree = ast.parse(path.read_text(encoding="utf-8"))
        modules = {
            node.module
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.module
        }
        self.assertIn("studio_module_api", modules)
        self.assertNotIn("studio_module_runtime", modules)

    def test_signed_adapter_preserves_route_and_delegates_pages_lazily(self):
        page_factory = Mock(return_value="existing-page")
        host = ModuleRuntimeHost(self.store, lambda _id, _action: True, services={
            "legacy_workflow": workflow_for_mode, "legacy_page_factory": page_factory})
        self.addCleanup(host.unload, "pinterest")
        registration = host.activate("pinterest", "1.0.0")
        original = workflow_for_mode("pinterest")
        page_factory.assert_not_called()
        self.assertIs(host.invoke_command("pinterest", "workflow"), original)
        self.assertEqual(tuple(page.name for page in registration.pages),
                         tuple(step.value for step in original.page_steps))
        for page in original.pages:
            handle = host.create_page("pinterest", page.step.value, "fixture")
            self.assertEqual(handle.value, "existing-page")
            handle.close()
            page_factory.assert_called_with("pinterest", page.component_id, "fixture")
        self.assertEqual(original.processing_operations, ())
        self.assertEqual(original.export_ids, ("png", "jpeg"))

    def test_missing_module_grant_cannot_activate_copied_signed_package(self):
        factory = Mock()
        host = ModuleRuntimeHost(self.store, services={"legacy_page_factory": factory})
        with self.assertRaises(ModuleAuthorizationError):
            host.activate("pinterest", "1.0.0")
        self.assertIsNone(self.store.state("pinterest")["active"])
        factory.assert_not_called()


if __name__ == "__main__":
    unittest.main()
