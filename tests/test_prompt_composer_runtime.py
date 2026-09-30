"""Composer runs only from a verified on-demand module package."""
import sys

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from PyQt6.QtWidgets import QApplication

from studio_module_packaging import prepare_module_release
from studio_module_runtime import ModuleAuthorizationError, ModuleRuntimeError, ModuleRuntimeHost
from studio_modules import ModuleStore
from studio_prompt_composer_host import PromptComposerHost
from studio_prompt_composer_package import COMPOSER_PAYLOAD, composer_payload


@pytest.fixture
def runtime(tmp_path):
    key = Ed25519PrivateKey.generate()  # Ephemeral test signer; no publisher key material.
    public = key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    files = composer_payload(root)
    assert set(files) == {'entry.py', *COMPOSER_PAYLOAD}
    package = prepare_module_release(
        module_id='prompt-composer', version='1.0.0', studio_min='3.2.8',
        studio_max_exclusive='3.3.0', platforms=['linux-x64'], entrypoint='entry.py',
        files=files, key_id='test', private_key=key,
    )
    path = tmp_path / 'composer.zip'
    path.write_bytes(package)
    store = ModuleStore(tmp_path / 'modules', studio_version='3.2.8',
                        platform='linux-x64', trusted_keys={'test': public})
    store.install(path)
    store.activate('prompt-composer', '1.0.0')
    allowed = {'load', 'command:kernel', 'page:main'}
    host = ModuleRuntimeHost(store, lambda module, action: module == 'prompt-composer' and action in allowed)
    return host, allowed


def test_verified_package_kernel_page_and_leases(runtime, tmp_path):
    app = QApplication.instance() or QApplication([])
    host, allowed = runtime
    host.load_active('prompt-composer')
    kernel = host.invoke_command('prompt-composer', 'kernel')
    assert kernel.validate_draft.__module__.startswith('_studio_module_prompt_composer_')
    assert len(kernel.catalogue()['templates']) == 21
    service = PromptComposerHost(tmp_path / 'library', settings_provider=lambda: {},
                                 authorize=lambda: True, runtime=host, kernel=kernel)
    page_handle = host.create_page('prompt-composer', 'main', service)
    page = page_handle.value
    assert page.__class__.__module__.startswith('_studio_module_prompt_composer_')
    assert page.generate_local() and len(page._variants) == 7
    with pytest.raises(ModuleRuntimeError):
        host.unload('prompt-composer')
    allowed.remove('page:main')
    with pytest.raises(ModuleAuthorizationError):
        host.create_page('prompt-composer', 'main', service)
    page._dirty = False
    page.deleteLater()
    app.processEvents()
    service.close()
    page_handle.close()
    host.unload('prompt-composer')
    assert not any(name.startswith('_studio_module_prompt_composer_') for name in sys.modules)


def test_core_has_no_eager_module_import():
    import ast
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    for name in ('studio_prompt_composer_host.py', 'studio_prompt_composer_storage.py',
                 'studio_prompt_composer_ai.py', 'studio_prompt_composer_api.py'):
        tree = ast.parse((root / name).read_text())
        assert not any(isinstance(node, (ast.Import, ast.ImportFrom)) and
                       ((isinstance(node, ast.ImportFrom) and (node.module or '').startswith('prompt_composer')) or
                        (isinstance(node, ast.Import) and any(alias.name.startswith('prompt_composer') for alias in node.names)))
                       for node in tree.body)
