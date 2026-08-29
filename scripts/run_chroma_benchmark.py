"""Run the deterministic, network-free Local Chroma Key baseline benchmark."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from chroma_benchmark import BenchmarkManifestError, load_manifest, run_benchmark
from chroma_key import remove_chroma_key


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run the offline Local Chroma Key quality benchmark.",
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=PROJECT_ROOT / "benchmarks" / "chroma" / "manifest.json",
    )
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args(argv)

    try:
        manifest = load_manifest(args.manifest)
        report = run_benchmark(
            manifest,
            remove_chroma_key,
            args.output_dir,
            algorithm_name="rgb-distance-baseline",
        )
    except (BenchmarkManifestError, OSError, ValueError) as error:
        print(f"Benchmark error: {error}", file=sys.stderr)
        return 2
    metrics_path = args.output_dir / "baseline_metrics.json"
    sheet_path = args.output_dir / "baseline-contact-sheet.png"
    print(f"Cases: {len(report['cases'])}")
    print(f"Metrics: {metrics_path}")
    print(f"Contact sheet: {sheet_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
