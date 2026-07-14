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

## User-Owned Fixture Gate

The gate was completed with:

- `C:\Users\belou\Downloads\Gemini_Generated_Image_fmj7lefmj7lefmj7.png`, a
  912x1147 RGBA image with the visible Gemini sparkle;
- `C:\Users\belou\Downloads\New folder\ready\tiny-water-droplet-1.png`, an
  unmarked clipart fixture.

The detector found the owned Gemini mark at confidence `0.694789` and did not fire
on the unmarked clipart. Automatic-mask and rectangle-mask `cv2` runs both changed
zero pixels outside their supplied masks. The automatic mask changed 3,237 pixels
inside the mark region; its bbox was `(832, 1067, 48, 48)`. The source and output
were both RGBA with fully opaque alpha. A direct pixel diff confirmed that all
3,237 changed pixels lie within the automatic mask bbox; the source file was not
modified.

The external CLI preview was not used as acceptance evidence because its renderer
displayed the opaque output incorrectly in the preview. The decoded pixel and alpha
checks above are authoritative for this benchmark.
