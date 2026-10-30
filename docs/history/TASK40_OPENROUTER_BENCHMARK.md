# Task 40: OpenRouter Managed-API Fallback Benchmark

## Current Status

Task 40 is complete. One separately authorized OpenRouter generation was made
on 2026-07-16. The response reported an actual cost of `$0.035`. The live path
is closed again in code with `TASK40_AUTHORIZED_GENERATION_ATTEMPTS = 0`, and
the persistent state records the single attempt as consumed.

This prototype is isolated in
`scripts/run_openrouter_regeneration_benchmark.py`. It does not change
`main.py`, the UI, application settings, or the production processing pipeline.

## Candidate Snapshot

The current OpenRouter Image API and endpoint records were re-checked on
2026-07-16. The selected non-Google candidate is
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

The input, raw provider result, report, and comparisons are stored outside git in
`C:\Users\belou\Downloads\output\task40-openrouter-regeneration`.

The result was evaluated for dimensions, alpha, per-tile RGB change,
SSIM, text accuracy, metadata, C2PA, cost, latency, and Task 38 pixel-marker
status. Raw provider bytes are preserved before analysis.

## OpenRouter Result

| Metric | Recraft V4.1 Utility |
| --- | --- |
| Response-reported cost | `$0.035` |
| API round-trip latency | `12.588 s` |
| Provider output | `1024x1024` RGB lossless WebP |
| Alpha | Lost; `261,101` source non-opaque pixels became opaque |
| Global SSIM | `0.177527` |
| RGB pixels changed by more than 2 | `99.9579%` |
| SynthID / unknown pixel marker | `not_verified`; removal not claimed |

Manual review failed every preservation-critical class:

- the photo was replaced by a different product scene;
- the face was replaced by a different person and composition;
- the illustration geometry remained only loosely recognizable;
- clipart transparency was flattened and the object was redesigned;
- exact text and numbers became unrelated or malformed text;
- the fine grid became a decorative waveform-like element.

The raw WebP contains `VP8L` image data plus a `CRFT` chunk. The `CRFT` block
contains an Ed25519 Recraft signature, provider identifier, generation timestamp,
and unique identifier. The report records only presence booleans and never stores
the signature or identifier values. This is provider provenance metadata, not
detector evidence about the source SynthID. C2PA validation was not performed.

## Comparison Table

| Provider/model | Listed cost | Result | Alpha/dimensions | Quality | Detector status |
| --- | ---: | --- | --- | --- | --- |
| KIE GPT Image 2 | `$0.030` | Completed in Task 39 | Alpha lost; `1254x1254` | Partial; content mostly preserved | `not_verified` |
| KIE FLUX 2 Pro | `$0.025` | Completed in Task 39 | Alpha lost; `1024x1024` | Failed; grid contaminated the board | `not_verified` |
| OpenRouter Recraft V4.1 Utility | `$0.035` response-reported | Completed | Alpha lost; `1024x1024` | Failed; scene/identity/text/clipart changed | `not_verified` |

None of the three managed candidates passes the universal quality and detector
gate. Recraft is not approved for the production application.

## Safety Controls

- The input is sent as a base64 data URL; the harness does not publish it to a
  temporary public URL.
- The provider is pinned to `recraft` and fallbacks are disabled.
- Live execution requires both `--allow-paid` and `OPENROUTER_API_KEY`.
- The authorization limit is zero again. Tests prove that the closed gate
  performs no network call.
- The authorized attempt used a process-independent state file under
  `%LOCALAPPDATA%\Clipart Generator\benchmarks`. It records `1/1` used,
  preventing retries from another output directory or process even if the
  code-level gate were reopened accidentally.
- Reports keep only allowlisted response fields. They never store the request
  prompt, reference data URL, response body, authorization header, or API key.
- Provider bytes are size-limited and validated as an image before analysis.

## Commands

Preparation only, already verified without a provider request:

```powershell
python scripts\run_openrouter_regeneration_benchmark.py --photo 'C:\Users\belou\Downloads\output\task37-visible-mark-acceptance-fixed\gemini-upstream-cleaned.png' --face 'C:\Users\belou\Downloads\output\task37-visible-mark-acceptance-fixed\gemini-owned-cleaned.png' --output-dir 'C:\Users\belou\Downloads\output\task40-openrouter-regeneration' --prepare-only
```

The single paid command used the same paths:

```powershell
$env:OPENROUTER_API_KEY = [Environment]::GetEnvironmentVariable('OPENROUTER_API_KEY','User'); python scripts\run_openrouter_regeneration_benchmark.py --photo 'C:\Users\belou\Downloads\output\task37-visible-mark-acceptance-fixed\gemini-upstream-cleaned.png' --face 'C:\Users\belou\Downloads\output\task37-visible-mark-acceptance-fixed\gemini-owned-cleaned.png' --output-dir 'C:\Users\belou\Downloads\output\task40-openrouter-regeneration' --allow-paid
```

The benchmark command read the key from the local environment. The key does not
appear in the command, report, fixtures, diff, or git history.

An already generated file can be analyzed without a key or provider request:

```powershell
python scripts\run_openrouter_regeneration_benchmark.py --photo '<photo.png>' --face '<face.png>' --output-dir '<evidence-dir>' --existing-result '<provider-output.png>'
```

## Decision

OpenRouter Recraft V4.1 Utility is a **no-go** for whole-image regeneration in
this application:

- it does not preserve the source subject or identity;
- it does not preserve exact text;
- it flattens alpha;
- it adds signed Recraft provenance metadata;
- it provides no detector evidence that SynthID or another hidden pixel marker
  is absent.

No OpenRouter provider is added to the application. Task 41 must now compare
the completed managed-API evidence and decide whether to activate the
conditional local/GPU path.

The final state passes 10 focused tests and all 108 project tests. Three review
passes found and fixed the pre-read size guard, stale test-count documentation,
and RIFF-boundary validation; no blocking or important finding remains open.
