"""Core-only frozen-shell boundary checked by the installed entrypoint smoke."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import sys


EXCLUDED_IMPLEMENTATIONS = (
    "studio_builtin_workflows",
    "v3_clipart_flow",
    "v3_processing_flow",
    "v3_pinterest_flow",
    "studio_auto_clipart_flow",
    "prompt_composer",
)


def frozen_shell_has_no_workflow_sources() -> bool:
    """Reject compiled workflow code or copied source in an installed shell.

    Source runs deliberately retain those files for module publishing and
    compatibility tests. PyInstaller exposes bundled bytecode through its
    import finder, even when the corresponding .py files are not on disk.
    """
    if not getattr(sys, "frozen", False):
        return True
    root = Path(getattr(sys, "_MEIPASS", ""))
    if not root.is_dir():
        return False
    for name in EXCLUDED_IMPLEMENTATIONS:
        try:
            if importlib.util.find_spec(name) is not None:
                return False
        except (ImportError, ValueError):
            return False
        if (root / f"{name}.py").exists() or (root / name).exists():
            return False
    return True
