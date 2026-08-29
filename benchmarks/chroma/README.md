# Local Chroma Key benchmark

This directory defines the deterministic, network-free quality gate used before
replacing the current RGB-distance remover.

Run from the repository root:

```bash
python scripts/run_chroma_benchmark.py \
  --output-dir .benchmark/chroma-baseline
```

The runner creates exact synthetic inputs, reference alpha masks, expected
foreground RGB, `baseline_metrics.json`, and `baseline-contact-sheet.png`.
The canonical VDS baseline is committed under `baseline-vds/`; experimental
runs should use `.benchmark/` or another ignored temporary output directory.
The canonical PNG files are read back and checked against SHA-256 values in the
manifest; ordinary benchmark runs never regenerate them.

Changing the golden set is deliberately separate and explicit:

```bash
python scripts/update_chroma_golden.py \
  --manifest benchmarks/chroma/manifest.json \
  --yes-update-golden
```

Every such update must be reviewed together with the PNG and hash diff before
the baseline is run again.

The contact sheet shows every case as input, expected transparency, actual
checkerboard, black, white, and bright-magenta previews. Numerical comparison
uses alpha MAE, alpha IoU, opaque-subject loss, background leakage, and RGB
damage. Performance is measured separately at the manifest's full-resolution
size in an isolated process: one warm-up plus three measured runs, reported as
the median. The report records peak process memory, platform, Python, Pillow,
NumPy, Git revision, and whether the working tree was dirty.

## Continue/stop rule

A replacement engine gets at most two bounded improvement cycles. It continues
only when it satisfies every gate in `manifest.json`: meaningful mean alpha-MAE
improvement, improvement in most cases, no material clean-edge or opaque-subject
regression, bounded runtime, and bounded memory. Otherwise the current engine
remains unchanged and the result is recorded as a stop decision.

The committed VDS baseline is evidence, not a universal performance promise.
Windows timing and process-memory evidence is collected again during the manual
acceptance pass.

The fixtures and benchmark implementation are original project work generated
with Pillow and NumPy. Clipbrook was previously studied as a research reference;
none of its files, code fragments, constants, tests, or assets are included.
