# Visible Mark Inpainting Benchmark

Task 32 currently has a bounded CPU result only. The benchmark uses the same
confirmed masks from Task 31 and never writes over source images.

Command:

```powershell
python scripts\benchmark_visible_inpainting.py `
  --manifest $env:TEMP\task32-manifest.json `
  --output $env:TEMP\task32-results.json `
  --backends cv2
```

## Current Result

On the two reproducible marked fixtures, `cv2` completed for both automatic and
rectangular masks. It changed zero pixels outside the supplied mask in all four
runs. Automatic masks changed fewer pixels than the rectangular fallback on both
fixtures. Runtime was approximately 0.6-1.9 seconds per run on this machine.

The fallback policy is therefore provisionally `cv2` plus a user-confirmed mask;
this is a safety property, not a claim that `cv2` gives the best texture fill.

MI-GAN and LaMa were not run automatically: invoking the package's optional backend
resolution attempted to obtain model resources and exceeded the bounded benchmark
window. They remain unselected until their weights are explicitly installed and
licensed for evaluation.

The required visual comparison on user-owned marked fixtures remains open. The
upstream demo/sample images used here are reproducible evaluation assets, not user
production files.
