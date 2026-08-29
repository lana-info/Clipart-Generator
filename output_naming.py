"""Pure output filename rules shared by processing workers and UI tests."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class WorkspaceLayout:
    root: Path
    rough: Path
    output: Path
    transient: Path


def workspace_layout(saved_path: str | Path) -> WorkspaceLayout:
    """Resolve the 3.1 workspace, migrating a legacy literal `output` path."""
    path = Path(saved_path).expanduser()
    root = path.parent if path.name.casefold() == "output" else path
    return WorkspaceLayout(
        root=root,
        rough=root / "rough",
        output=root / "output",
        transient=root / ".run",
    )


def processed_output_path(output_dir: str | Path, source_path: str | Path, run_stamp: str, *, overwrite: bool) -> Path:
    """Return a destination, preserving existing files unless overwrite is enabled."""
    base = Path(source_path).stem
    destination = Path(output_dir) / f"{base}_ready.png"
    if overwrite or not destination.exists():
        return destination
    suffix = 2
    while True:
        candidate = destination.with_name(f"{base}_ready_{suffix}.png")
        if not candidate.exists():
            return candidate
        suffix += 1


def generated_output_path(
    output_dir: str | Path,
    row_index: int,
    prompt: str = "",
) -> Path:
    words = re.findall(r"[^\W_]+", str(prompt).casefold(), flags=re.UNICODE)[:3]
    prompt_stem = "_".join(words)[:48].strip("_") or "clipart"
    base = f"{prompt_stem}_{max(1, int(row_index)):02d}_ready"
    destination = Path(output_dir) / f"{base}.png"
    suffix = 2
    while destination.exists():
        destination = Path(output_dir) / f"{base}_{suffix}.png"
        suffix += 1
    return destination
