"""Reconnect finished pictures to an Auto Clipart set without generating anything.

A run can lose its results (a new run was started and stopped, a project was reopened after a version change), while
the finished PNG files still lie in the result folder. This module only *finds* such files; the flow asks the owner
before it attaches them. It never scans outside the result folder, never follows links and never touches a file."""
from __future__ import annotations

import re
from pathlib import Path

# «<subject>_<NN>_ready.png»; a re-created copy gets «_ready_2.png». NN is the 1-based position in the set.
READY_NUMBER = re.compile(r"_(\d{2,})_ready(?:_\d+)?\.png$", re.IGNORECASE)
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def _safe_png(path: Path, output_dir: Path) -> bool:
    try:
        if path.is_symlink() or not path.is_file() or path.suffix.lower() != ".png" or path.stat().st_size < 64:
            return False
        if path.resolve().parent != output_dir.resolve():
            return False
        with open(path, "rb") as handle:
            return handle.read(8) == PNG_SIGNATURE
    except OSError:
        return False


def scan_ready_outputs(output_dir, count: int) -> dict[int, Path]:
    """{0-based set position: newest finished PNG} found in the result folder (top level only)."""
    folder = Path(output_dir)
    found: dict[int, tuple[float, Path]] = {}
    try:
        entries = list(folder.iterdir())
    except OSError:
        return {}
    for path in entries:
        match = READY_NUMBER.search(path.name)
        if not match or not _safe_png(path, folder):
            continue
        position = int(match.group(1)) - 1
        if not 0 <= position < count:
            continue
        try:
            stamp = path.stat().st_mtime
        except OSError:
            continue
        if position not in found or stamp > found[position][0]:
            found[position] = (stamp, path.resolve())
    return {position: path for position, (_stamp, path) in found.items()}


def archived_outputs(previous_runs, prompts, output_dir) -> dict[int, Path]:
    """{position: PNG} from earlier runs saved in the project, matched by the prompt itself."""
    folder = Path(output_dir)
    result: dict[int, Path] = {}
    for entry in reversed(list(previous_runs or ())):
        try:
            recorded, rows = entry["prompts"], entry["run"]
        except (KeyError, TypeError):
            continue
        for index, row in enumerate(rows):
            if index >= len(recorded) or row.get("status") != "succeeded" or not row.get("output_path"):
                continue
            path = Path(row["output_path"])
            if not _safe_png(path, folder):
                continue
            for position, prompt in enumerate(prompts):
                if position not in result and prompt == recorded[index]:
                    result[position] = path.resolve()
                    break
    return result


def recoverable(session_items, prompts, previous_runs, output_dir, *, is_done) -> dict[int, Path]:
    """What can be reconnected: positions without a finished picture, with a finished PNG on disk."""
    wanted = [index for index, item in enumerate(session_items) if not is_done(item)]
    if not wanted:
        return {}
    found = dict(scan_ready_outputs(output_dir, len(session_items)))
    found.update(archived_outputs(previous_runs, prompts, output_dir))  # the project's own record wins
    return {index: found[index] for index in wanted if index in found}
