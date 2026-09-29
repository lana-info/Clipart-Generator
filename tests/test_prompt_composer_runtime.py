import threading
import pytest
from studio_modules import ModuleStore
from studio_module_api import ModuleRegistration, PageDeclaration
from studio_module_runtime import ModuleRuntimeHost, ModuleRuntimeError, ModuleAuthorizationError


def host(tmp_path, authorize=lambda *_: True):
    store = ModuleStore(tmp_path, studio_version='3.2.0', platform='linux', trusted_keys={})
    bundled = ModuleRegistration('prompt-composer', '1.0.0', pages=(PageDeclaration('main', lambda: object()),))
    return ModuleRuntimeHost(store, authorize, bundled=(bundled,))


def test_bundled_auth_and_leases(tmp_path):
    runtime = host(tmp_path)
    runtime.activate('prompt-composer')
    page = runtime.create_page('prompt-composer', 'main')
    job = runtime.acquire_job_lease('prompt-composer')
    with pytest.raises(ModuleRuntimeError):
        runtime.unload('prompt-composer')
    page.close()
    with pytest.raises(ModuleRuntimeError):
        runtime.unload('prompt-composer')
    job.close()
    job.close()
    runtime.unload('prompt-composer')
    runtime.load_active('prompt-composer')
    with pytest.raises(ModuleRuntimeError):
        runtime.activate('prompt-composer', '2.0.0')


def test_denied_at_each_boundary(tmp_path):
    allowed = False
    runtime = host(tmp_path, lambda *_: allowed)
    with pytest.raises(ModuleAuthorizationError):
        runtime.activate('prompt-composer')
    allowed = True
    runtime.activate('prompt-composer')
    allowed = False
    with pytest.raises(ModuleAuthorizationError):
        runtime.create_page('prompt-composer', 'main')
    runtime.unload('prompt-composer')


def test_only_host_thread_can_open(tmp_path):
    runtime = host(tmp_path)
    runtime.activate('prompt-composer')
    errors = []
    def open_page():
        try:
            runtime.create_page('prompt-composer', 'main')
        except ModuleRuntimeError as exc:
            errors.append(exc)
    thread = threading.Thread(target=open_page)
    thread.start()
    thread.join()
    assert len(errors) == 1
