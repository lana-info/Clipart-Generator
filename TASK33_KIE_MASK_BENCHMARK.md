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
preserving every other pixel and the original style. The result records task
latency, listed cost, output dimensions, changed pixels outside the mask, and output
metadata. API keys are never written to the result or progress logs.

## Live Provider Attempts

The user authorized at most five requests. Three provider attempts were made and no
further requests were needed:

1. The documented 4o payload with one `filesUrl` plus `maskUrl` was rejected before
   generation with `maskUrl requires multiple filesUrl`.
2. A compatibility attempt with source and mask in `filesUrl` plus `maskUrl` was
   rejected before generation with `parameter error`.
3. One `gpt-image/1.5-image-to-image` task used the source and binary mask as two
   input references, with an explicit prompt to edit only the black mask area. This
   generated one output. It is a prompted mask-reference comparison, not proof that
   the documented native 4o mask endpoint works.

The successful call was listed at approximately `$0.02` for one medium image and
completed in `102.485` seconds. The two rejected requests produced no generation
result; billing for them was not inferred from the API response.

## Comparison Result

The identical owned Gemini fixture and detected `48x48` mask were used for local and
KIE comparisons. The source was padded from `912x1147` to `912x1368` (`2:3`) without
resizing its content.

| Measurement | Local `cv2` | KIE GPT Image 1.5 |
| --- | ---: | ---: |
| Changed pixels outside supplied mask | `0` | `817,034` |
| Outside-mask changed ratio | `0%` | `78.3491%` |
| Normalization-only baseline | n/a | `2.5936%` |
| Changed pixels inside mask | `3,237` | `3,251` |
| Output latency | under 2 seconds in Task 32 runs | `102.485` seconds |
| Successful paid generations | `0` | `1` |

The normalization baseline measures the expected pixel delta from resizing the
source to the provider's `1023x1537` output and back. It is far below the KIE delta,
so output-size normalization does not explain the `78.3491%` outside-mask change.

Manual inspection confirmed that the sparkle was removed, but the face, hair, skin,
shirt texture, and framing were regenerated outside the mask. The output was an RGB
PNG at approximately 300 DPI with no alpha, EXIF, or ICC profile.

## Decision

KIE is rejected as the visible-mark fallback for precise masked cleanup. Local
`cv2` remains safer because it changes no pixels outside the supplied mask. The KIE
result can still inform the separate hidden-marker whole-image regeneration tasks,
where changing the whole image is expected rather than a failure.

The reproducible harness is `scripts/run_kie_mask_benchmark.py`. Its
`--existing-result` mode repeats all pixel and metadata analysis without reading the
desktop API key or making another request. Generated images and reports remain
outside git under the user's output folder.
