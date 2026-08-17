"""Fail-closed scan for accidentally tracked secret-bearing artifacts."""

from __future__ import annotations

import argparse
import subprocess
from pathlib import Path


BLOCKED_NAMES = {".env", "licenses.db"}
BLOCKED_SUFFIXES = (".pem", ".p12", ".pfx", ".key")
BLOCKED_MARKERS = ("-----BEGIN PRIVATE KEY-----", "aws_secret_access_key")


def scan_paths(paths: list[Path], *, allowed: set[str] = frozenset()) -> list[str]:
    findings: list[str] = []
    for path in paths:
        relative = path.as_posix()
        if relative in allowed:
            continue
        if path.name in BLOCKED_NAMES or path.suffix.lower() in BLOCKED_SUFFIXES:
            findings.append(f"blocked sensitive path: {relative}")
            continue
        try:
            content = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        if any(marker in content for marker in BLOCKED_MARKERS):
            findings.append(f"credential-like material: {relative}")
    return findings


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("paths", nargs="*")
    parser.add_argument("--allow-path", action="append", default=[])
    parser.add_argument("--git-tracked", action="store_true")
    args = parser.parse_args()
    paths = [Path(item) for item in args.paths]
    if args.git_tracked:
        output = subprocess.check_output(["git", "ls-files"], text=True)
        paths.extend(Path(item) for item in output.splitlines())
    findings = scan_paths(paths, allowed=set(args.allow_path))
    for finding in findings:
        print(finding)
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
