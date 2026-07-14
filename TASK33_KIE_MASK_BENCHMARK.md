# Task 33: KIE Mask-Edit Benchmark

## Safe Preparation

The official KIE 4o Image API contract was checked before any paid request:

- endpoint: `POST https://api.kie.ai/api/v1/gpt4o-image/generate`;
- authentication: Bearer API key;
- edit inputs: `filesUrl`, `maskUrl`, `prompt`;
- KIE mask semantics: black pixels are edited and white pixels remain unchanged;
- supported output ratios: `1:1`, `3:2`, and `2:3`.

Source: <https://docs.kie.ai/4o-image-api/quickstart> and
<https://docs.kie.ai/4o-image-api/generate-4-o-image>.

## Impact on Our Fixtures

The owned Gemini fixture used by Task 32 is `912x1147`, approximately `0.795:1`,
which is not one of KIE's supported ratios. Sending it directly would require an
implicit crop or resize and would make a comparison against local `cv2` invalid.
The paid benchmark must therefore use one of these explicitly recorded modes:

1. pad the source and mask to a supported ratio, then remove the padding locally;
2. use a fixture already matching `2:3` and compare only the returned content area;
3. reject KIE 4o as a fair arbitrary-aspect-ratio fallback.

The smallest useful paid experiment is one `2:3` marked fixture, one identical
binary mask, and one prompt requesting only removal of the marked overlay while
preserving every other pixel and the original style. The result must record task
latency, billed cost, output dimensions, changed pixels outside the mask, and output
metadata. API keys must never be written to the result or progress logs.

No live request, upload, or credit consumption was performed during this preparation.
