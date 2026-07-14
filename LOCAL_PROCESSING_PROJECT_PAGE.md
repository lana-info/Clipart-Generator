# Local Processing Project Page

Source spec: [`PROCESSING_PIPELINE_TZ.md`](./PROCESSING_PIPELINE_TZ.md).

Implementation checklist: [`TASKS.md`](./TASKS.md).

Change history: [`CHANGELOG.md`](./CHANGELOG.md).

## What This Adds

- Independent Local Real-ESRGAN/KIE upscale passes before and after background removal.
- Optional Unsharp Mask after upscale.
- Local rembg background removal.
- Local rembg edge quality presets: `Soft`, `Normal`, `Sharp`.
- Experimental Local BEN2 background removal with hard alpha controls.
- PhotoRoom Standard background removal as an optional paid quality fallback.
- Edge contour removal with `1/2/3 px`.
- KIE fallback.
- Local-only processing without a KIE API key.
- Mixed local/KIE processing flows.

## Author Quick Setup

1. Put `realesrgan-ncnn-vulkan-20211212-windows/` in the project folder.
2. In processing settings, choose `Local Real-ESRGAN`.
3. For clipart, choose `Clipart` and start with `2x`; use `4x` when quality matters more than speed. Local Real-ESRGAN supports `2x` and `4x` here.
4. If the upscaled watercolor looks too soft, enable `Unsharp Mask` after upscale. Start with `Amount 30`, `Radius 100`, `Threshold 0`.
5. For background removal, start with `Local BEN2 (experimental)` when clipart needs a cleaner cut than rembg.
6. For BEN2, start with `refine foreground` off, `alpha threshold 24`, `softness 0 px`, `radius 0 px`.
7. If BEN2 leaves jagged corners, try `radius 1 px`; use `2-3 px` only if the silhouette still looks too rough.
8. Keep `softness 0 px` when the output must have a hard edge with no semi-transparent aura.
9. Enable `Удалять контур` and start with `1 px`; use `2-3 px` only when a visible white edge remains.
10. When local removal quality is insufficient, enter the PhotoRoom API key in Settings and select `PhotoRoom Standard`.
11. A fully local or PhotoRoom-only processing run does not require a KIE API key. Mixed local/KIE runs still need the key for the selected KIE step.

## Fixed Processing Order

The processing order is fixed:

1. Optional upscale before background removal.
2. Optional Unsharp Mask.
3. Remove background.
4. Optional upscale after background removal.
5. Edge contour removal.
6. Final trim.

Each upscale pass has its own provider and scale/model. The UI shows the combined multiplier, for example `2x + 2x = 4x` or `4x + 4x = 16x`.

## BEN2 Test

BEN2 is evaluated with a standalone script before adding it to the app.

Install test dependencies:

```powershell
python -m pip install torch torchvision transformers pillow
python -m pip install git+https://github.com/PramaLLC/BEN2.git
```

Run on one or more images:

```powershell
python .\scripts\test_ben2_background.py "C:\path\image.png" --output-dir "C:\path\ben2-test"
```

Compare the generated `_ben2.png` and `_dark_preview.png` files against Photoroom and Local rembg.
