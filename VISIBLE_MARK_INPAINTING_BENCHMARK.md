# Visible Mark Inpainting Benchmark

Task 32 established a bounded CPU baseline. Task 37 later completed the production
quality gate. Both stages use confirmed masks and never write over source images.

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

Task 34 provisionally selected `cv2` as the bounded local provider: automatic
masks are allowed only for Gemini, while other small service marks require a
user-confirmed bounded mask. Task 37 visual inspection at normal size and 200%
found visible rectangular patches in that production path, so the final
implementation no longer uses `cv2.inpaint` for removal.

MI-GAN and LaMa were not available during the Task 32 baseline. Task 37 later
evaluated the official MIT-licensed MI-GAN ONNX model linked by the
[`Picsart-AI-Research/MI-GAN`](https://github.com/Picsart-AI-Research/MI-GAN)
project. The pinned model is now bundled and runs locally through ONNX Runtime;
LaMa remains unselected.

## Task 37 Production Acceptance

The final production path uses reverse-alpha reconstruction for the known Gemini
overlay and bounded local MI-GAN for a user-confirmed service label. Nine fixtures
were checked: two marked Gemini images, one confirmed Doubao label, five clean
upstream images, and one clean user-owned clipart. All three marked fixtures were
changed only inside their masks; all six clean fixtures remained unchanged and
created no output. Source hashes, dimensions, image modes, and alpha were
preserved. Normal-size and 200% comparison sheets passed visual inspection, with
zero KIE/API requests.

Acceptance evidence is stored outside git in
`C:\Users\belou\Downloads\output\task37-visible-mark-acceptance-fixed`.

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
