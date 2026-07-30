"""Pure output filename rules shared by processing workers and UI tests."""

from __future__ import annotations

from pathlib import Path


def processed_output_path(output_dir: str | Path, source_path: str | Path, run_stamp: str, *, overwrite: bool) -> Path:
    """Return the destination for a processed source without touching the filesystem."""
    base = Path(source_path).stem
    filename = f"{base}_processed.png" if overwrite else f"{base}_processed_{run_stamp}.png"
    return Path(output_dir) / filename
