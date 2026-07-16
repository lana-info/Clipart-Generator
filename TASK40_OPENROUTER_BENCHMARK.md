# Task 40: OpenRouter Managed-API Fallback Benchmark

## Current Status

The benchmark is prepared but no OpenRouter generation has been made. The live
path is closed in code with `TASK40_AUTHORIZED_GENERATION_ATTEMPTS = 0` until the
user separately authorizes one paid request and configures an OpenRouter key.

This prototype is isolated in
`scripts/run_openrouter_regeneration_benchmark.py`. It does not change
`main.py`, the UI, application settings, or the production processing pipeline.

## Candidate Snapshot

The current OpenRouter Image API and endpoint records were checked on
2026-07-15. The selected non-Google candidate is
`recraft/recraft-v4.1-utility`:

- accepts one image reference and returns an image at approximately 1K;
- is served by the single `recraft` provider;
- has an authoritative endpoint price snapshot of `$0.035` per output image;
- is described as restrained and suitable for structured visuals;
- has no documented guarantee that it removes SynthID or another hidden pixel
  marker;
- has no documented provider pixel-watermark policy in the checked model and
  endpoint records.

The benchmark therefore starts and remains at `not_verified`. Successful image
generation cannot be reported as watermark removal.

Sources:

- [OpenRouter dedicated Image API](https://openrouter.ai/docs/guides/overview/multimodal/image-generation)
- [Recraft V4.1 Utility model page](https://openrouter.ai/recraft/recraft-v4.1-utility)
- [Current per-endpoint capability and pricing record](https://openrouter.ai/api/v1/images/models/recraft/recraft-v4.1-utility/endpoints)

## Fixture And Rubric

Task 40 reuses the exact Task 39 fixture builder, prompt, dimensions, and
analysis functions. The prepared `1024x1024` RGBA board includes:

- photo and face;
- illustration;
- clipart with real transparency;
- exact text and numbers;
- color swatches and a fine-line grid.

The no-network preparation artifacts are stored outside git in
`C:\Users\belou\Downloads\output\task40-openrouter-regeneration`.

The future result is evaluated for dimensions, alpha, per-tile RGB change,
SSIM, text accuracy, metadata, C2PA, cost, latency, and Task 38 pixel-marker
status. Raw provider bytes are preserved before analysis.

## Comparison Table

| Provider/model | Listed cost | Result | Alpha/dimensions | Quality | Detector status |
| --- | ---: | --- | --- | --- | --- |
| KIE GPT Image 2 | `$0.030` | Completed in Task 39 | Alpha lost; `1254x1254` | Partial; content mostly preserved | `not_verified` |
| KIE FLUX 2 Pro | `$0.025` | Completed in Task 39 | Alpha lost; `1024x1024` | Failed; grid contaminated the board | `not_verified` |
| OpenRouter Recraft V4.1 Utility | `$0.035` snapshot | Not run | Pending | Pending | `not_verified` |

No production decision can be made until the OpenRouter row has a real result,
manual quality review, and available detector evidence.

## Safety Controls

- The input is sent as a base64 data URL; the harness does not publish it to a
  temporary public URL.
- The provider is pinned to `recraft` and fallbacks are disabled.
- Live execution requires both `--allow-paid` and `OPENROUTER_API_KEY`.
- The current authorization limit is zero. Tests prove that the closed gate
  performs no network call and creates no attempt reservation.
- If one attempt is later authorized, a process-independent state file under
  `%LOCALAPPDATA%\Clipart Generator\benchmarks` is reserved before network I/O.
  A failed provider call consumes that attempt, preventing retries from another
  output directory or process.
- Reports keep only allowlisted response fields. They never store the request
  prompt, reference data URL, response body, authorization header, or API key.
- Provider bytes are size-limited and validated as an image before analysis.

## Commands

Preparation only, already verified without a provider request:

```powershell
python scripts\run_openrouter_regeneration_benchmark.py --photo 'C:\Users\belou\Downloads\output\task37-visible-mark-acceptance-fixed\gemini-upstream-cleaned.png' --face 'C:\Users\belou\Downloads\output\task37-visible-mark-acceptance-fixed\gemini-owned-cleaned.png' --output-dir 'C:\Users\belou\Downloads\output\task40-openrouter-regeneration' --prepare-only
```

The future single paid command will use the same arguments with
`--allow-paid`. It is intentionally rejected until a separate authorization is
recorded in code. The key must be supplied only through the
`OPENROUTER_API_KEY` environment variable, never in a command argument or chat.

An already generated file can be analyzed without a key or provider request:

```powershell
python scripts\run_openrouter_regeneration_benchmark.py --photo '<photo.png>' --face '<face.png>' --output-dir '<evidence-dir>' --existing-result '<provider-output.png>'
```

## Blocker

The remaining Task 40 acceptance work requires:

1. a separate user authorization for exactly one OpenRouter request with a
   maximum listed cost of `$0.035`;
2. `OPENROUTER_API_KEY` configured locally outside the repository.

Until both exist, no paid call is permitted and Task 40 remains in progress.

The prepared state passes 6 focused tests and all 104 project tests. An
independent code/security review reported `PASS`.
