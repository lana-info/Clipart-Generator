# Task 39: KIE Whole-Image Regeneration Benchmark

## Scope And Request Limit

The benchmark tests whole-image regeneration only. It does not change the
application pipeline or claim that a hidden pixel watermark was removed.

The user authorized at most five provider attempts across the related KIE
experiments. Task 33 used three attempts. Task 39 used the remaining two:

1. `gpt-image-2-image-to-image` at `1K`.
2. `flux-2/pro-image-to-image` at `1K`, used only after GPT Image 2 failed the
   alpha and dimension requirements.

The persistent evidence ledger records a total of five attempts. After the second
Task 39 result, the checked-in harness was closed to live generation at the code
level, so changing `--output-dir` or starting another process cannot create a sixth
request. `--prepare-only` and `--existing-result` remain available without network
generation.

## Fixture

One `1024x1024` owned/approved comparison board covered all required classes in
two paid generations:

- photographic subject;
- face;
- procedural illustration;
- procedural clipart with real alpha transparency;
- exact text, numbers, punctuation, and small text;
- color swatches and a fine-line grid.

The input was RGBA and contained `261,101` non-opaque pixels. Generated files,
raw provider bytes, reports, comparisons, and the request ledger remain outside
git in `C:\Users\belou\Downloads\output\task39-kie-regeneration`.

## Results

Prices below are documented/listed snapshots, not billing evidence.

| Model | Listed credits | Listed 1K cost | KIE task latency (upload excluded) | Provider output | Alpha | Global SSIM |
| --- | ---: | ---: | ---: | --- | --- | ---: |
| GPT Image 2 image-to-image | `6` | `$0.030` | `99.497 s` | `1254x1254` RGB PNG | lost | `0.424396` |
| FLUX 2 Pro image-to-image | `5` | `$0.025` | `67.568 s` | `1024x1024` RGB PNG | lost | `0.245487` |

The documented snapshot total is `11 credits / $0.055`; provider billing was not
queried or inferred.

Manual review at normal size:

| Class | GPT Image 2 | FLUX 2 Pro |
| --- | --- | --- |
| Photo | Recognizable and visually close, but regenerated | Visually close, but covered by an added grid |
| Face | Identity and expression mostly preserved | Identity mostly preserved, but grid contamination is visible |
| Illustration | Layout and colors mostly preserved | Base illustration preserved, but grid contamination is visible |
| Text-heavy | All required fixture text remained readable and exact | Required tile text remained readable, but extra malformed/duplicated text appeared elsewhere |
| Clipart + alpha | Shape remained recognizable; transparency became a baked checkerboard | Shape/layout changed; transparency became an opaque grid background |
| Color/fine detail | Usable but restyled | Control grid spread over the complete board and corrupted the layout |

GPT Image 2 was the better visual result, but it changed the requested dimensions
and flattened alpha. FLUX preserved `1024x1024`, but it treated the control grid as
global content, altered the composition, and also flattened alpha. Neither model
passes as a universal photo/illustration/text/face/clipart regeneration provider.

## Metadata And Pixel-Marker Status

- GPT output contained an embedded PNG C2PA container (`caBX`, `24,918` bytes),
  with no EXIF, XMP, IPTC, ICC, DPI, or detected generator field.
- FLUX output contained an embedded PNG C2PA container (`caBX`, `26,445` bytes),
  one comments/text item, and one detected generator field.
- C2PA presence was inspected but signatures were not validated.
- Metadata/C2PA presence does not prove any pixel-level watermark result.

The official Gemini SynthID verification flow is an authenticated, manual file
handoff and was not callable from this benchmark environment. The known
Gemini-origin source and both provider outputs therefore remain `not_verified`.
Processing completion is recorded separately, and `removed` is not claimed.

Official verification references:

- [Gemini Apps Help: check whether an image was generated or edited by Google AI](https://support.google.com/gemini/answer/16722517?hl=en)
- [Google DeepMind: SynthID](https://deepmind.google/models/synthid/)

## Decision

KIE is a **no-go** for universal hidden pixel-watermark regeneration:

- GPT Image 2 may be useful only as an explicitly lossy photo/illustration
  regeneration experiment;
- FLUX 2 Pro is rejected for this workflow;
- neither model preserves transparent clipart;
- neither model has detector evidence that a target pixel marker is absent;
- both outputs added an embedded C2PA container.

Task 40 is activated to compare one current non-Google OpenRouter candidate using
the same fixture and status contract. No KIE provider is added to the production
UI by this task.

## Reproduction

Preparation without a provider request:

```powershell
python scripts\run_kie_regeneration_benchmark.py --photo 'C:\Users\belou\Downloads\output\task37-visible-mark-acceptance-fixed\gemini-upstream-cleaned.png' --face 'C:\Users\belou\Downloads\output\task37-visible-mark-acceptance-fixed\gemini-owned-cleaned.png' --output-dir 'C:\Users\belou\Downloads\output\task39-kie-regeneration' --prepare-only
```

The two live commands used the same arguments plus, respectively:

```powershell
--model gpt-image-2-image-to-image --allow-paid
--model flux-2/pro-image-to-image --allow-paid
```

Those commands document the completed historical runs. The current harness rejects
any new `--allow-paid` run because the authorized budget is exhausted.

Provider contracts:

- [KIE GPT Image 2 image-to-image](https://docs.kie.ai/market/gpt/gpt-image-2-image-to-image)
- [KIE FLUX 2 Pro image-to-image](https://docs.kie.ai/market/flux2/pro-image-to-image)

The recorded FLUX request used the documented example value
`nsfw_checker=false` on the owned safe fixture. Review then aligned the reusable
benchmark with the production app and enabled the checker for any future run. The
request limit was exhausted, so no paid rerun was made for this non-quality
parameter.

`--existing-result` can repeat the pixel, alpha, metadata, C2PA, and status
analysis without reading the desktop API key or creating another provider task.
