# Visible Mark Detector Evaluation

Task 31 evaluates `lana-info/remove-ai-watermarks` outside the application. No
detector, model, or dependency from that repository is imported by `main.py`.

## Evaluated Revision

- Repository: <https://github.com/lana-info/remove-ai-watermarks>
- Evaluated commit: `190dc89d234fd7e3a61ff755f01251c9c0b87ef0`
- License: Apache-2.0; any future integration must retain the upstream license and
  attribution. Model weights and optional backends require a separate license review.
- Installed mode: isolated editable package with `--no-deps`; the application
  environment was not changed in its dependency manifests.

## Reproduction

The probe stores JSON with detection flags, confidence, usual location, bounding
region, elapsed time, and binary masks only. It does not save cleaned images.

```powershell
python scripts\probe_visible_marks.py `
  --manifest $env:TEMP\task31-manifest.json `
  --output $env:TEMP\task31-results.json `
  --mask-dir $env:TEMP\task31-masks
```

The manifest used upstream's reproducible demo/sample fixtures: one Gemini marked
image, one Doubao marked image, and five unmarked images covering generated-photo,
illustration, and textured/varied corners. Task 32 later added one user-owned Gemini
marked image and one user-owned unmarked clipart fixture.

## Results

| Fixture group | Expected | Detected | Result |
| --- | ---: | ---: | --- |
| Gemini demo | 1 | 1 | 1/1 true positive |
| Doubao sample | 1 | 1 | 1/1 true positive |
| Unmarked demo/sample images | 0 | 0 | 0/5 false positives |

Measured detector time was approximately 1.2-4.3 seconds per image on this
Windows/Python environment. The Gemini and Doubao masks were written to the
temporary mask directory; no mask is committed to the repository.

Jimeng and Samsung are not claimed as measured: no owned or reproducible full-image
fixtures for those marks were available in this run. This result is sufficient to
continue to the separate inpainting benchmark, but it is not an approval to add the
detector to production.

## Decision

The localizer is technically lightweight and showed no false positives on the five
upstream fixtures or the later user-owned unmarked fixture. Task 34 approves
automatic integration only for Gemini, which has both upstream and user-owned
marked evidence. Doubao and unmeasured marks require a user-confirmed bounded mask.
