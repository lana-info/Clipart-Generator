# Local Processing Project Page

Source spec: [`PROCESSING_PIPELINE_TZ.md`](./PROCESSING_PIPELINE_TZ.md).

Implementation checklist: [`TASKS.md`](./TASKS.md).

Change history: [`CHANGELOG.md`](./CHANGELOG.md).

## What This Adds

- Local Real-ESRGAN upscale.
- Optional Unsharp Mask after upscale.
- Local rembg background removal.
- Local rembg edge quality presets: `Soft`, `Normal`, `Sharp`.
- Edge contour removal with `1/2/3 px`.
- KIE fallback.
- Local-only processing without a KIE API key.
- Mixed local/KIE processing flows.

## Author Quick Setup

1. Put `realesrgan-ncnn-vulkan-20211212-windows/` in the project folder.
2. In processing settings, choose `Local Real-ESRGAN`.
3. For clipart, choose `Clipart` and start with `2x`; use `4x` when quality matters more than speed.
4. If the upscaled watercolor looks too soft, enable `Unsharp Mask` after upscale. Start with `Amount 30`, `Radius 100`, `Threshold 0`.
5. For background removal, choose `Local rembg` + `Clipart`.
6. Keep `rembg edge` on `Normal` first; try `Soft` for too-harsh edges or `Sharp` for dirty semi-transparent halos.
7. Enable `Удалять контур` and start with `1 px`; use `2-3 px` only when a visible edge remains.
8. A fully local processing run does not require a KIE API key. Mixed local/KIE runs still need the key for the selected KIE step.

## Fixed Processing Order

The processing order is fixed:

1. Upscale.
2. Optional Unsharp Mask.
3. Remove background.
4. Edge contour removal.
5. Final trim.
