"""Explicit signed-payload inventory for the optional Patterns module."""
import ast
from pathlib import Path

from studio_modules import MAX_PACKAGE_BYTES, ModulePackageError


# Engine sources stay at the repository root (and keep their tests); the signed
# package gets copies whose sibling imports are rewritten to relative imports.
PATTERNS_ENGINE = ("studio_patterns.py", "studio_patterns_tools.py")
PATTERNS_ENTRY = "studio_patterns_entry.py"


def _source(root, name):
    path = root / name
    if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_PACKAGE_BYTES:
        raise ModulePackageError("Invalid Patterns source")
    return path


def patterns_payload(source_root):
    """Return package-relative names mapped to the exact bytes to be signed."""
    root = Path(source_root)
    owned = {Path(name).stem for name in PATTERNS_ENGINE}
    files = {"entry.py": _source(root, PATTERNS_ENTRY).read_bytes()}
    for name in PATTERNS_ENGINE:
        tree = ast.parse(_source(root, name).read_text(encoding="utf-8"), filename=name)
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.level == 0 and node.module in owned:
                node.level = 1
            elif isinstance(node, ast.Import) and any(alias.name in owned for alias in node.names):
                raise ModulePackageError("Patterns-owned imports must use from syntax")
        files[name] = ast.unparse(tree).encode("utf-8")
    return files
