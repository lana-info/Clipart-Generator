# Task 42: Local remove-ai-watermarks Feasibility

## Decision

The local whole-image diffusion path is a **production hardware no-go on the
current computer**. Do not add SDXL, ControlNet, or Qwen regeneration to the
desktop application and do not start Tasks 43-49 from this result.

The audit stopped before model loading:

- model-weight downloads: `0` bytes;
- paid API requests: `0`;
- generated outputs: `0`;
- main application dependencies changed: no;
- `main.py` or UI changed: no.

This is not a claim that upstream cannot start plain SDXL on CPU or that the
pipelines cannot work on suitable GPU hardware. Upstream documents a slow CPU
path, but Task 42 excludes CPU-only inference as a production candidate. That
diagnostic run was not attempted because of the current memory/resource risk,
so plain-SDXL technical CPU impossibility is not claimed. Task 42 did not
produce an approved pipeline for deployment.

## Evaluated Inputs

The source checkout was pinned and clean. Before the final preflight, the
official Hugging Face metadata API verified each model's exact SHA, card license,
and every selected weight filename/size below. Only bounded JSON metadata was
read; no model weights were downloaded.

| Component | Revision | License | Selected serialized weights |
|---|---|---|---:|
| [`lana-info/remove-ai-watermarks`](https://github.com/lana-info/remove-ai-watermarks) | `190dc89d234fd7e3a61ff755f01251c9c0b87ef0` | Apache-2.0 | source only |
| [`stabilityai/stable-diffusion-xl-base-1.0`](https://huggingface.co/stabilityai/stable-diffusion-xl-base-1.0) | `462165984030d82259a11f4367a4eed129e94a7b` | CreativeML Open RAIL++-M | `13,875,688,436` bytes (`12.92 GiB`) for the FP32 Diffusers components selected by the CPU path |
| [`xinsir/controlnet-canny-sdxl-1.0`](https://huggingface.co/xinsir/controlnet-canny-sdxl-1.0) | `1271357eda52d54b857c650cacb5b51144643ccb` | Apache-2.0 component; combined pipeline also loads SDXL under Open RAIL++-M | `2,502,139,104` bytes (`2.33 GiB`) for the default safetensors file |
| [`Qwen/Qwen-Image`](https://huggingface.co/Qwen/Qwen-Image) | `75e0b4be04f60ec59a75f475837eced720f823b6` | Apache-2.0 | `57,699,249,390` bytes (`53.74 GiB`) |
| [`madebyollin/sdxl-vae-fp16-fix`](https://huggingface.co/madebyollin/sdxl-vae-fp16-fix) | `207b116dae70ace3637169f1ddd2434b91b3a8cd` | MIT card metadata, but derived from SDXL-VAE; inherited SDXL obligations are unresolved | `334,643,238` bytes; not used by the local FP32 path |

The SDXL size is the sum of the default FP32 Diffusers text encoder, second text
encoder, UNet, and VAE files, not the repository's duplicate single-file,
OpenVINO, or FP16 variants. The ControlNet total is SDXL plus its default
ControlNet file: `16,377,827,540` bytes (`15.25 GiB`).

## Isolated Environment

The environment was created outside the application repository:

| Item | Result |
|---|---|
| Location | `D:\WorkOS\Clipart Generator-task42\.venv-locked` |
| Python | `3.12.6` |
| remove-ai-watermarks | `0.14.1`, editable pinned checkout |
| torch | `2.12.1+cpu` |
| diffusers | `0.39.0` |
| transformers | `5.13.0` |
| Upstream focused tests | `26 passed` |
| Hugging Face cache | isolated on drive D and forced offline during preflight |

Neither `requirements.txt` nor `requirements-dev.txt` in Clipart Generator was
changed.

## Hardware Evidence

| Item | Measured value |
|---|---|
| OS | Windows 11, AMD64 |
| Physical RAM | `19,275,145,216` bytes (`17.95 GiB`) |
| Available RAM at locked preflight | volatile and recorded per run in the external JSON; every measured value remained below the `12.92 GiB` smallest selected weight set |
| Display adapter | AMD Radeon(TM) Graphics, reported `2 GiB` adapter RAM |
| CUDA build / devices | none / `0` |
| XPU | unavailable |
| MPS | unavailable |
| NVIDIA tooling | `nvidia-smi` unavailable |

The pinned upstream accepts only `cpu`, `mps`, `cuda`, or `xpu`. It has no
DirectML device path for the installed AMD adapter. On CPU it explicitly selects
FP32 for all three profiles.

The upstream model IDs are **not** loaded with a `revision=` argument. The model
SHAs in this report pin the audited Hugging Face snapshots, but the current
upstream loader does not enforce them. Any future GPU worker must pass the exact
revisions or prefetch and verify those snapshots before switching the cache to
offline mode. The upstream also contains automatic dependency/CUDA repair code,
which is another reason it must never run inside the desktop application's
environment.

## Pipeline Comparison

| Pipeline | Minimum audited weights | Hardware result | Runtime/VRAM/RAM | Output quality, dimensions, alpha | Detector result |
|---|---:|---|---|---|---|
| Plain SDXL | `12.92 GiB` | `not_run_local_production_no_go` | CPU diagnostic not run because of resource risk; technical CPU impossibility is not claimed | not measured | `not_verified` |
| SDXL + Canny ControlNet | `15.25 GiB` | `not_run_local_production_no_go` | insufficient safe RAM headroom before activations/OS | not measured | `not_verified` |
| Qwen-Image 20B | `53.74 GiB` serialized BF16 | `not_run_local_production_no_go` | serialized weights exceed `17.95 GiB` total RAM; upstream CPU path requests FP32 | not measured | `not_verified` |

CPU inference was not started because Task 42 already excludes CPU-only
execution as a production candidate. Downloading `12.92-53.74 GiB` to force an
unusable, pagefile-heavy run would add risk without satisfying the acceptance
gate.

No local official SynthID pixel decoder is available. Even a successful future
diffusion run must remain `not_verified` until the output is checked with an
appropriate external/official detector; successful processing cannot be
reported as watermark removal.

## License Obligations

- Preserve the upstream Apache-2.0 license and required notices when copying or
  distributing its code.
- SDXL weights are not Apache-2.0. Any future worker must include and comply with
  the CreativeML Open RAIL++-M terms and use restrictions.
- The xinsir ControlNet component declares Apache-2.0, but its working pipeline
  also loads SDXL. The combined service must preserve and enforce SDXL's Open
  RAIL++-M obligations; ControlNet metadata does not replace them.
- Qwen-Image weights/code declare Apache-2.0; preserve that license and
  attribution when redistributed.
- The optional FP16 VAE declares MIT, but its model card says it is based on
  SDXL-VAE. Do not rely on MIT metadata alone to dismiss inherited SDXL terms;
  keep SDXL obligations and obtain a license review before packaging/hosting it.
- No model weights are bundled or redistributed by the desktop application in
  this task, so these are future deployment obligations rather than new package
  contents.

## Reproducible Commands

```powershell
git ls-remote https://github.com/lana-info/remove-ai-watermarks.git refs/heads/main
git clone --no-tags --single-branch --branch main https://github.com/lana-info/remove-ai-watermarks.git 'D:\WorkOS\Clipart Generator-task42\remove-ai-watermarks'
git -C 'D:\WorkOS\Clipart Generator-task42\remove-ai-watermarks' rev-parse HEAD

$env:UV_CACHE_DIR='D:\WorkOS\Clipart Generator-task42\.uv-cache'
$env:UV_PROJECT_ENVIRONMENT='D:\WorkOS\Clipart Generator-task42\.venv-locked'
uv sync --locked --extra gpu --extra dev

$env:HF_HOME='D:\WorkOS\Clipart Generator-task42\hf-home'
$env:HF_HUB_OFFLINE='1'
$env:TRANSFORMERS_OFFLINE='1'
$env:DIFFUSERS_OFFLINE='1'
& 'D:\WorkOS\Clipart Generator-task42\.venv-locked\Scripts\python.exe' -m pytest tests/test_invisible_engine.py tests/test_optional_deps.py -q
& 'D:\WorkOS\Clipart Generator-task42\.venv-locked\Scripts\python.exe' 'D:\WorkOS\Clipart Generator\scripts\run_local_watermark_feasibility.py' --upstream-dir 'D:\WorkOS\Clipart Generator-task42\remove-ai-watermarks' --output 'D:\WorkOS\Clipart Generator-task42\evidence\task42-local-feasibility-locked.json' --verify-model-metadata

python -m unittest tests.test_local_watermark_feasibility -v
python -m py_compile .\main.py .\scripts\run_local_watermark_feasibility.py
$env:QT_QPA_PLATFORM='offscreen'; python -m unittest discover -s tests -v
$env:QT_QPA_PLATFORM='offscreen'; python -c "import main; app=main.QApplication([]); w=main.MainWindow(); print('SMOKE_OK'); w.close(); app.quit()"
```

The generated machine-readable evidence remains outside git at
`D:\WorkOS\Clipart Generator-task42\evidence\task42-local-feasibility-locked.json`.

An initial range-resolved `uv pip install -e '.[gpu]'` check was superseded by
the final `uv sync --locked` environment above. Neither environment downloaded
model weights.

## Verification

- Task 42 focused tests: `13 passed`.
- Official model metadata: all 4 revisions, card licenses, and selected file
  sizes verified; model-weight downloads `0`.
- Pinned upstream focused tests: `26 passed`.
- Full Clipart Generator suite: `149 passed`.
- Python compilation: passed for `main.py` and the Task 42 preflight.
- Offscreen application main flow: `SMOKE_OK`.
- `git diff --exit-code -- requirements.txt requirements-dev.txt main.py`:
  passed; production code and dependency files are unchanged.
- No root `README.md` exists in this checkout. The review used the current
  `README_AUTHOR_SHORT.md`, `PROJECT_KNOWLEDGE_BASE.md`, `PRD.md`, `TASKS.md`,
  `CHANGELOG.md`, and `CLEANUP_CAPABILITY_MATRIX.md`.

## Product Outcome

Tasks 43-49 are skipped because there is no Task 42-approved pipeline to deploy
or expose. The application keeps its verified metadata/C2PA cleanup and bounded
visible-mark cleanup. Hidden pixel-level markers remain unsupported for
guaranteed removal; no experimental whole-image regeneration control is added.
