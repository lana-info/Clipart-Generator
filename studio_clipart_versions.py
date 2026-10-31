"""Auto Clipart owner review: marks, notes and earlier versions of a picture.

Pure file/state logic without Qt. A version is a copy of a replaced final PNG in
<output>/versions; only files recorded here are ever restored or deleted.
"""
from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path

MARKS = ("ok", "bad_generation", "bad_cutout", "deleted")
VERSION_REASONS = ("ok", "bad_generation", "bad_cutout", "deleted")
MAX_NOTE = 500
MAX_PROMPT = 4000
MAX_PATH = 4000
MAX_VERSIONS = 10  # bounded: the project file is limited to 2 MB
VERSION_KEYS = {"path", "original", "reason", "note", "prompt", "created"}


def versions_dir(output_dir) -> Path:
    return Path(output_dir) / "versions"


def validate_review_row(row: dict) -> None:
    """Raise ValueError for a malformed saved review; absent keys mean defaults."""
    mark = row.get("review_mark", "ok")
    if mark not in MARKS:
        raise ValueError("Неверная метка картинки")
    if not isinstance(row.get("review_checked", False), bool):
        raise ValueError("Неверная отметка проверки картинки")
    if not isinstance(row.get("prompt_edited", False), bool):
        raise ValueError("Неверная отметка исправленного промпта")
    note = row.get("review_note", "")
    if not isinstance(note, str) or len(note) > MAX_NOTE:
        raise ValueError("Неверная заметка картинки")
    versions = row.get("versions", [])
    if not isinstance(versions, list) or len(versions) > MAX_VERSIONS:
        raise ValueError("Неверная история версий картинки")
    for entry in versions:
        if not isinstance(entry, dict) or set(entry) != VERSION_KEYS:
            raise ValueError("Неверная версия картинки")
        if (any(not isinstance(entry[key], str) for key in VERSION_KEYS)
                or not entry["path"] or len(entry["path"]) > MAX_PATH
                or len(entry["original"]) > MAX_PATH
                or entry["reason"] not in VERSION_REASONS
                or len(entry["note"]) > MAX_NOTE or len(entry["prompt"]) > MAX_PROMPT
                or len(entry["created"]) > 40):
            raise ValueError("Неверная версия картинки")


def review_fields(item) -> dict:
    """Saved form of the review; defaults are omitted so old projects stay unchanged.

    getattr: an older Studio core has RunItem without the review fields.
    """
    fields = {}
    if getattr(item, "review_mark", "ok") != "ok":
        fields["review_mark"] = item.review_mark
    if getattr(item, "review_checked", False):
        fields["review_checked"] = True
    if getattr(item, "review_note", ""):
        fields["review_note"] = item.review_note
    if getattr(item, "prompt_edited", False):
        fields["prompt_edited"] = True
    if getattr(item, "versions", None):
        fields["versions"] = [dict(entry) for entry in item.versions]
    return fields


def restore_review(item, row: dict) -> None:
    item.review_mark = row.get("review_mark", "ok")
    item.review_checked = bool(row.get("review_checked", False))
    item.review_note = row.get("review_note", "")
    item.prompt_edited = bool(row.get("prompt_edited", False))
    item.versions = [dict(entry) for entry in row.get("versions", [])]


def _safe_file(path: Path) -> bool:
    return not path.is_symlink() and path.is_file() and path.suffix.lower() == ".png"


def _within(path: Path, root: Path) -> bool:
    try:
        path.resolve(strict=False).relative_to(root.resolve(strict=False))
    except (OSError, ValueError):
        return False
    return True


def _version_target(folder: Path, source: Path) -> Path:
    for number in range(1, 10000):
        candidate = folder / f"{source.stem}.v{number}.png"
        if not candidate.exists():
            return candidate
    raise ValueError("Слишком много версий картинки")


def keep_version(item, output_dir, prompt: str = "", *, now: datetime | None = None) -> bool:
    """Copy the current picture into versions; the item's mark and note move with it.

    Returns False when there is no current picture to keep.
    """
    current = Path(item.output_path) if item.output_path else None
    if current is None or not _safe_file(current):
        return False
    if len(item.versions) >= MAX_VERSIONS:
        raise ValueError("У картинки слишком много версий. Очистите корзину и повторите.")
    folder = versions_dir(output_dir)
    folder.mkdir(parents=True, exist_ok=True)
    if folder.is_symlink() or not _within(folder, Path(output_dir)):
        raise ValueError("Папка версий недоступна")
    target = _version_target(folder, current)
    shutil.copy2(current, target)
    item.versions.append({
        "path": str(target.resolve()),
        "original": str(current.resolve()),
        "reason": item.review_mark if item.review_mark in VERSION_REASONS else "ok",
        "note": item.review_note[:MAX_NOTE],
        "prompt": str(prompt or "")[:MAX_PROMPT],
        "created": (now or datetime.now()).isoformat(timespec="seconds"),
    })
    item.review_mark = "ok"
    item.review_checked = False  # a replaced picture has to be looked at again
    item.review_note = ""
    return True


def _recorded_version(item, index: int, output_dir) -> Path:
    if not 0 <= index < len(item.versions):
        raise ValueError("Версия не найдена")
    path = Path(item.versions[index]["path"])
    if not _within(path, versions_dir(output_dir)) or not _safe_file(path):
        raise ValueError("Файл версии недоступен")
    return path


def restore_version(item, index: int, output_dir, prompt: str = "", *,
                    now: datetime | None = None) -> Path:
    """Make a saved version current; the replaced current picture becomes a version."""
    source = _recorded_version(item, index, output_dir)
    record = item.versions[index]
    current = Path(item.output_path) if item.output_path else None
    if current is not None and _safe_file(current):
        target = current  # may be an editor copy recorded as the current output
    elif record["original"] and _within(Path(record["original"]), Path(output_dir)):
        target = Path(record["original"])
    else:
        raise ValueError("Вернуть версию можно только в папку результата")
    if target.is_symlink():
        raise ValueError("Вернуть версию можно только в папку результата")
    snapshot = (list(item.versions), item.review_mark, item.review_checked, item.review_note)
    staged = target.with_name(target.name + ".restore")
    kept = None
    try:
        keep_version(item, output_dir, prompt, now=now)
        if len(item.versions) > len(snapshot[0]):
            kept = Path(item.versions[-1]["path"])
        shutil.copy2(source, staged)
        staged.replace(target)  # the one step an antivirus lock can refuse (WinError 32)
    except BaseException:
        # the picture on disk is still the old one: keep the item exactly as it was
        staged.unlink(missing_ok=True)
        if kept is not None:
            kept.unlink(missing_ok=True)
        item.versions[:] = snapshot[0]
        item.review_mark, item.review_checked, item.review_note = snapshot[1:]
        raise
    restored = item.versions.pop(index)
    item.output_path = str(target.resolve())
    item.review_mark = "ok"
    item.review_checked = False
    item.review_note = ""
    try:
        source.unlink()
    except OSError:
        pass  # the picture is already restored; a leftover copy in versions/ is harmless
    return Path(restored["path"])


def discard_last_version(item, output_dir) -> None:
    """Drop the newest version record and its recorded file (a rejected attempt)."""
    if not item.versions:
        return
    entry = item.versions.pop()
    path = Path(entry["path"])
    if _within(path, versions_dir(output_dir)) and _safe_file(path):
        path.unlink()


def trash_paths(items, output_dir) -> tuple[list[Path], list[Path]]:
    """Files that 'empty trash' would delete: deleted pictures and recorded versions."""
    deleted, versions = [], []
    root, folder = Path(output_dir), versions_dir(output_dir)
    for item in items:
        if item.review_mark == "deleted" and item.output_path:
            path = Path(item.output_path)
            if _within(path, root) and _safe_file(path):
                deleted.append(path)
        for entry in item.versions:
            path = Path(entry["path"])
            if _within(path, folder) and _safe_file(path):
                versions.append(path)
    return deleted, versions


def empty_trash(items, output_dir) -> int:
    """Delete only recorded files; version records are dropped, deleted marks stay."""
    deleted, versions = trash_paths(items, output_dir)
    removed = 0
    for path in deleted + versions:
        try:
            path.unlink()
            removed += 1
        except FileNotFoundError:
            pass
    gone = {str(path) for path in deleted}
    for item in items:
        item.versions = [entry for entry in item.versions if Path(entry["path"]).exists()]
        if item.output_path and item.output_path in gone:
            item.output_path = ""
            item.editor_output_path = ""
    return removed
