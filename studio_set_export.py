"""Explicit per-set archives. No inference of set membership or alpha quality."""
import hashlib
import os
from pathlib import Path
import tempfile
from zipfile import ZipFile, ZIP_DEFLATED

from PIL import Image
from studio_delivery import (
    create_contact_sheet_pdf, output_filename, slug_from_title, transliterate_ru,
)


class ExportCancelled(RuntimeError):
    pass


def archive_basename(project_name, set_title, names=None, count=None):
    """'<project>-set-<set>[-<count>]' as a safe English file name (no extension).

    The owner 2026-10-29: the archive name is the project, the set and the bare
    number of pictures at the end (``…-set-maxi-42``); no date is added here —
    a date can only come from the project name itself.
    """
    names = names or {}
    def english(text):
        return names.get(text, text)
    project = slug_from_title(english(project_name), max_words=10) if project_name.strip() else ''
    set_slug = slug_from_title(english(set_title), max_words=10)
    if set_slug.split('-')[0] == 'set' and len(set_slug) > 4:
        set_slug = set_slug[4:]
    project, set_slug = project[:70].strip('-'), set_slug[:45].strip('-')
    base = f'{project}-set-{set_slug}' if project else f'set-{set_slug}'
    if count is not None:
        base = f'{base}-{int(count)}'
    return base.strip('-_.')


def export_folder(destination) -> Path:
    """The published folder is «clipart set»; a repeated export gets a bare number."""
    destination = Path(destination)
    candidate, suffix = destination / 'clipart set', 2
    while candidate.exists():
        candidate = destination / f'clipart set {suffix}'
        suffix += 1
    return candidate


def export_clipart_sets(sets, destination, *, cancelled=lambda: False, exported_hashes=None,
                        project_name='', names=None, progress=None):
    """Publish a fresh folder only after all ZIPs are complete.

sets is a list of {title: str, images: list[path]}. Caller supplies reviewed
final PNGs and explicit membership. ``names`` maps original names (project,
sets, image stems) to English; unmapped Cyrillic is transliterated.
"""
    names = dict(names or {})
    project_name = str(project_name or '')
    used_archives = set()
    destination = Path(destination)
    def check_cancelled():
        if cancelled():
            raise ExportCancelled('Экспорт отменён. Архивы не опубликованы.')
    check_cancelled()
    if not destination.is_dir():
        raise ValueError('Выберите существующую папку экспорта')
    if not isinstance(sets, list) or not 1 <= len(sets) <= 100:
        raise ValueError('Допускается от 1 до 100 наборов')
    prepared = []
    snapshots = {}
    for group in sets:
        if (not isinstance(group, dict) or set(group) != {'title', 'images'}
                or not isinstance(group['title'], str) or not group['title'].strip()
                or len(group['title']) > 4000 or not isinstance(group['images'], list)
                or not 1 <= len(group['images']) <= 1000):
            raise ValueError('Неверное описание набора')
        paths = [Path(p) for p in group['images']]
        if len({p.resolve() for p in paths}) != len(paths):
            raise ValueError('Один файл указан в наборе несколько раз')
        prepared.append((group['title'], paths))
    output = export_folder(destination)
    # Staging keeps incomplete archives invisible to delivery consumers.
    with tempfile.TemporaryDirectory(prefix='.clipart-export-', dir=destination) as temporary:
        staging = Path(temporary)
        bundles = staging / 'bundles'
        bundles.mkdir()
        for number, (title, paths) in enumerate(prepared, 1):
            check_cancelled()
            if progress is not None:
                progress(number - 1, len(prepared), f'Создаю набор {number} из {len(prepared)}')
            with tempfile.TemporaryDirectory(prefix='set-', dir=staging) as set_temp:
                work = Path(set_temp)
                copied = []
                for ordinal, source in enumerate(paths, 1):
                    check_cancelled()
                    if not source.is_file() or source.stat().st_size > 64 * 1024 * 1024:
                        raise ValueError('PNG отсутствует или превышает 64 МБ')
                    # Freeze bytes once: contact sheet and archive describe the same snapshot.
                    with source.open('rb') as handle:
                        data = handle.read(64 * 1024 * 1024 + 1)
                    if len(data) > 64 * 1024 * 1024:
                        raise ValueError('PNG превышает 64 МБ')
                    name = output_filename(ordinal, names.get(source.stem, source.stem))
                    target = work / name
                    target.write_bytes(data)
                    source_key = str(source.resolve())
                    fingerprint = hashlib.sha256(data).hexdigest()
                    if source_key in snapshots and snapshots[source_key] != fingerprint:
                        raise ValueError('PNG изменился во время экспорта')
                    snapshots[source_key] = fingerprint
                    with Image.open(target) as image:
                        if image.format != 'PNG' or image.width * image.height > 100_000_000:
                            raise ValueError('Экспорт принимает только PNG допустимого размера')
                        image.verify()
                    copied.append(target)
                set_english = transliterate_ru(names.get(title, title))
                header = (f"{transliterate_ru(names.get(project_name, project_name))} — Set {set_english}"
                          if project_name.strip() else f"Set {set_english}")
                sheet = create_contact_sheet_pdf(copied, work / 'overview.pdf', title=header)
                check_cancelled()
                base = archive_basename(project_name, title, names, count=len(paths))
                candidate, suffix = base, 2
                while candidate.casefold() in used_archives:
                    candidate = f'{base}-{suffix}'
                    suffix += 1
                used_archives.add(candidate.casefold())
                archive = bundles / f'{candidate}.zip'
                with ZipFile(archive, 'w', ZIP_DEFLATED) as zip_file:
                    for path in copied:
                        zip_file.write(path, f'png/{path.name}')
                    zip_file.write(sheet, 'overview.pdf')
                with ZipFile(archive) as zip_file:
                    if zip_file.testzip() is not None:
                        raise ValueError('Не удалось проверить архив')
        check_cancelled()
        if progress is not None:
            progress(len(prepared), len(prepared), 'Завершаю экспорт')
        os.rename(bundles, output)
    if exported_hashes is not None:
        exported_hashes.update(snapshots)
    return sorted(output.glob('*.zip'))
