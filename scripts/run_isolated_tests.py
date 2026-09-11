"""Run offline pytest with temporary desktop data, never real saved credentials.

Usage: python scripts/run_isolated_tests.py [-q] [tests/test_example.py]
Linux/Windows helper; native macOS paths require that platform's test harness.
"""
from pathlib import Path
import os
import sys
import tempfile


def main():
    if sys.platform == "darwin":
        raise SystemExit("Use the native macOS isolated test harness")
    root = Path(__file__).resolve().parents[1]
    os.chdir(root)
    sys.path.insert(0, str(root))
    with tempfile.TemporaryDirectory(prefix="vibix-isolated-tests-") as folder:
        os.environ["LOCALAPPDATA"] = folder
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        import pytest
        return pytest.main(sys.argv[1:] or ["-q"])


if __name__ == "__main__":
    raise SystemExit(main())
