"""Pure output filename rules shared by processing workers and UI tests."""

from __future__ import annotations

from pathlib import Path


def processed_output_path(output_dir: str | Path, source_path: str | Path, run_stamp: str, *, overwrite: bool) -> Path:
    """Return a destination, preserving existing files unless overwrite is enabled."""
    base = Path(source_path).stem
    destination = Path(output_dir) / f"{base}_processed.png"
    if overwrite or not destination.exists():
        return destination
    suffix = 2
    while True:
        candidate = destination.with_name(f"{base}_processed_{suffix}.png")
        if not candidate.exists():
            return candidate
        suffix += 1
