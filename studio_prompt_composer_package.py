"""Explicit signed-payload inventory for the optional Prompt Composer module."""
from pathlib import Path

from studio_modules import MAX_PACKAGE_BYTES, ModulePackageError


COMPOSER_PAYLOAD = (
    'prompt_composer/__init__.py',
    'prompt_composer/catalog.py',
    'prompt_composer/directions.py',
    'prompt_composer/scenario_people_products.py',
    'prompt_composer/scenario_other.py',
    'prompt_composer/engine.py',
    'prompt_composer/model.py',
    'prompt_composer/ui.py',
)


def composer_payload(source_root):
    """Return source bytes under their exact package-relative names."""
    root = Path(source_root)
    files = {}
    for name in ('prompt_composer/entry.py', *COMPOSER_PAYLOAD):
        source = root / name
        if source.is_symlink() or not source.is_file() or source.stat().st_size > MAX_PACKAGE_BYTES:
            raise ModulePackageError('Invalid Prompt Composer source')
        files['entry.py' if name.endswith('/entry.py') else name] = source.read_bytes()
    return files
