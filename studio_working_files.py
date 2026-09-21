"""Hash-bound ownership of disposable copies in a project's rough directory."""
import hashlib
import json
import os
from pathlib import Path
import tempfile


def digest(path):
    with Path(path).open('rb') as handle:
        return hashlib.file_digest(handle, 'sha256').hexdigest()


def write_receipt(workspace, run_id, records):
    rough = Path(workspace) / 'rough'
    if rough.is_symlink():
        raise ValueError('Working directory must not be a symbolic link')
    target = rough / f'.cleanup-{run_id}.json'
    _write(target, records)


def _write(target, records):
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=target.parent,
                                         delete=False) as handle:
            temporary = Path(handle.name)
            json.dump(records, handle)
        os.replace(temporary, target)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _receipts(workspace):
    rough = Path(workspace) / 'rough'
    if rough.is_symlink() or not rough.is_dir():
        return
    for path in rough.glob('.cleanup-*.json'):
        try:
            if path.is_symlink() or path.stat().st_size > 16 * 1024 * 1024:
                continue
            records = json.loads(path.read_text(encoding='utf-8'))
            if isinstance(records, list) and all(isinstance(r, dict) for r in records):
                yield path, records
        except (OSError, ValueError):
            continue


def link_edited_output(workspace, previous_keys, destination):
    previous = {str(Path(key).resolve()) for key in previous_keys if key}
    output = {'path': str(Path(destination).resolve()), 'sha256': digest(destination)}
    for receipt, records in _receipts(workspace):
        changed = False
        for record in records:
            owners = record.get('outputs', [])
            if isinstance(owners, list) and any(
                isinstance(owner, dict) and isinstance(owner.get('path'), str)
                and owner['path'] in previous for owner in owners
            ):
                record['outputs'] = [owner for owner in owners
                                     if isinstance(owner, dict) and owner.get('path') != output['path']]
                record['outputs'].append(output)
                changed = True
        if changed:
            _write(receipt, records)


def cleanup_working_files(workspace, exported, *, intermediates=False, originals=False):
    """Delete only unchanged owned copies for hash-matching exported finals.

    exported maps final paths to the hashes captured during successful export.
    Missing ownership, modified files and symbolic links are always retained.
    """
    deleted = 0
    skipped = 0
    categories = set()
    if intermediates:
        categories.add('intermediate')
    if originals:
        categories.add('generated')
    if not categories or workspace is None:
        return deleted, skipped
    receipts = list(_receipts(workspace))
    protected = set(exported)
    for _, records in receipts:
        for record in records:
            owners = record.get('outputs', [])
            if isinstance(owners, list):
                protected.update(owner['path'] for owner in owners
                                 if isinstance(owner, dict) and isinstance(owner.get('path'), str))
    for receipt, records in receipts:
        for record in records:
            owners = record.get('outputs', [])
            if not isinstance(owners, list) or not any(
                isinstance(owner, dict) and isinstance(owner.get('path'), str)
                and owner['path'] in exported
                and exported[owner['path']] == owner.get('sha256') for owner in owners
            ):
                continue
            files = record.get('files', [])
            if not isinstance(files, list):
                continue
            for item in files:
                if (not isinstance(item, dict) or not isinstance(item.get('category'), str)
                        or item['category'] not in categories):
                    continue
                name = item.get('name')
                if (not isinstance(name, str) or not name.startswith('rough_')
                        or not name.endswith('.png') or Path(name).name != name
                        or '/' in name or '\\' in name):
                    skipped += 1
                    continue
                path = receipt.parent / name
                try:
                    if path.is_symlink():
                        skipped += 1
                    elif not path.exists():
                        continue
                    elif str(path.resolve()) in protected or digest(path) != item.get('sha256'):
                        skipped += 1
                    else:
                        path.unlink()
                        deleted += 1
                except OSError:
                    skipped += 1
    return deleted, skipped
