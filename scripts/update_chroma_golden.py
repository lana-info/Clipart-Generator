"""Explicitly regenerate and re-hash the committed Local Chroma golden set."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from chroma_benchmark import BenchmarkManifestError, generate_fixture, load_manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Regenerate the immutable Local Chroma golden fixtures.",
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=PROJECT_ROOT / "benchmarks" / "chroma" / "manifest.json",
    )
    parser.add_argument("--yes-update-golden", action="store_true")
    args = parser.parse_args(argv)
    if not args.yes_update_golden:
        print(
            "Golden update refused: pass --yes-update-golden after reviewing the change.",
            file=sys.stderr,
        )
        return 2
    try:
        raw = json.loads(args.manifest.read_text(encoding="utf-8"))
        manifest = load_manifest(args.manifest)
        golden_dir = Path(manifest["_golden_dir"])
        hashes: dict[str, dict[str, str]] = {}
        for case in manifest["cases"]:
            fixture = generate_fixture(case, size=int(manifest["fixture_size"]))
            paths = {
                "input": golden_dir / "input" / f"{fixture.case_id}.png",
                "expected_mask": golden_dir
                / "expected-mask"
                / f"{fixture.case_id}.png",
                "expected_foreground": golden_dir
                / "expected-foreground"
                / f"{fixture.case_id}.png",
            }
            images = {
                "input": fixture.input_image,
                "expected_mask": fixture.expected_mask,
                "expected_foreground": fixture.expected_foreground,
            }
            for name, path in paths.items():
                _save_png_atomic(images[name], path)
            hashes[fixture.case_id] = {
                name: hashlib.sha256(path.read_bytes()).hexdigest()
                for name, path in paths.items()
            }
        raw["golden_sha256"] = hashes
        raw.setdefault("golden_dir", "golden")
        _write_json_atomic(raw, args.manifest)
    except (OSError, json.JSONDecodeError, BenchmarkManifestError, ValueError) as error:
        print(f"Golden update error: {error}", file=sys.stderr)
        return 2
    print(f"Updated {len(hashes)} golden cases in {golden_dir}")
    return 0


def _save_png_atomic(image, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(
        prefix=f".{destination.stem}.",
        suffix=".tmp",
        dir=destination.parent,
    )
    os.close(fd)
    temporary_path = Path(temporary)
    try:
        image.save(temporary_path, format="PNG")
        os.replace(temporary_path, destination)
    finally:
        temporary_path.unlink(missing_ok=True)


def _write_json_atomic(payload: dict[str, object], destination: Path) -> None:
    fd, temporary = tempfile.mkstemp(
        prefix=f".{destination.stem}.",
        suffix=".tmp",
        dir=destination.parent,
    )
    os.close(fd)
    temporary_path = Path(temporary)
    try:
        temporary_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary_path, destination)
    finally:
        temporary_path.unlink(missing_ok=True)


if __name__ == "__main__":
    raise SystemExit(main())
