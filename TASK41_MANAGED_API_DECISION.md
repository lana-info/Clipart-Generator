# Task 41: Managed-API Decision Gate

## Decision

Task 41 is complete. No managed whole-image regeneration API is approved for
the application. Task 42, the isolated local `remove-ai-watermarks` feasibility
check, is activated.

The production application, `main.py`, UI, settings, and processing pipeline
were not changed. The Task 41 harness remains an evidence-only script and its
live authorization list is closed again.

## Budget Outcome

The user approved a `$0.300` ceiling for the complete OpenRouter test series.
Task 40 had already reported `$0.035`, leaving a planned Task 41 maximum of
`$0.265`.

| Attempt | Endpoint snapshot | Response-reported cost | Result |
| --- | ---: | ---: | --- |
| Task 40 Recraft V4.1 Utility | `$0.035` | `$0.035` | Completed; rejected for fidelity |
| Seedream 4.5, native RGBA plus explicit options | `$0.040` | `$0.000` | HTTP 400; no image and no charge |
| Seedream 4.5, RGB with provider defaults | `$0.040` | `$0.040` | Completed |
| Riverflow 2.5 Pro, RGB at requested `1K` | `$0.130` | `$0.264885` | Completed; cost gate failed |

The two successful Task 41 responses total `$0.304885`; the authenticated key
record reports the same `usage_daily` value. Including Task 40, known billed
test spend is `$0.339885`, `$0.039885` above the approved series ceiling.

The overrun came from Riverflow: its response-reported cost was `$0.264885`,
although the immediately preceding authoritative endpoint record listed
`$0.130` for the requested default/`1K` output. That is about `2.04x` the
snapshot price. The local fail-closed state records `$0.379885` because it also
conservatively retains the unbilled `$0.040` reservation for the HTTP 400
attempt. No further paid request is authorized.

## Fidelity Results

### Seedream 4.5 RGB

- response cost: `$0.040`;
- API round trip: `24.522 s`;
- provider output: `2048x2048` RGB JPEG;
- alpha: lost;
- global SSIM after normalization: `0.977527`;
- C2PA: present;
- SynthID/unknown pixel marker: `not_verified`, removal not claimed.

Despite the high aggregate SSIM, manual inspection failed the identity/detail
gate. The photo and face were visibly re-rendered into a coarse, pixelated
style. Text was mostly preserved, but the output is not a faithful replacement
for arbitrary source images.

### Riverflow 2.5 Pro

- response cost: `$0.264885` against a `$0.130` endpoint snapshot;
- provider output: `1024x1024` RGB PNG;
- alpha: lost;
- global SSIM: `0.869615`;
- exact visible text: preserved in manual review;
- C2PA: not present;
- SynthID/unknown pixel marker: `not_verified`, removal not claimed.

Riverflow was the strongest visual result. It kept the subject, face, layout,
text, swatches, and fine grid recognizable and close to the source. It still
changed `73.107%` of RGB pixels by more than 2, flattened all source alpha, and
provided no detector evidence that a hidden pixel marker was removed. Its
response cost was also not bounded by the published endpoint snapshot.

Artifacts are outside git in:

`C:\Users\belou\Downloads\output\task41-managed-fidelity`

## Why Managed API Is Rejected

The managed candidates do not satisfy the complete gate:

- KIE GPT Image 2 changed dimensions and lost alpha;
- KIE FLUX 2 Pro contaminated the control grid and lost alpha;
- OpenRouter Recraft replaced the scene/identity/text and added signed Recraft
  provenance;
- Seedream changed identity/detail, lost alpha, and added C2PA;
- Riverflow had the best fidelity but lost alpha, remained `not_verified`, and
  reported more than twice its endpoint snapshot price.

An exact production per-image price threshold is therefore unnecessary for
selection: no candidate proves hidden-marker removal while preserving the
required image classes, and Riverflow additionally failed cost predictability.
No production managed-API spend is authorized.

## Final Safety State

The isolated harness is
`scripts/run_managed_fidelity_benchmark.py`. Its final state:

1. `TASK41_AUTHORIZED_CANDIDATES` is empty, so CLI paid generation is closed;
2. candidates and endpoint evidence remain available for offline analysis;
3. each request used one provider tag with fallbacks disabled;
4. endpoint capabilities and price were checked immediately before reservation;
5. the local state used an exclusive lock and one-shot candidate reservations;
6. source and provider bytes had size, pixel, side, decompression, and image
   validation limits;
7. HTTPS was pinned to `openrouter.ai`, redirects were rejected, and reports
   never stored the key, request image, raw response, or authorization header;
8. the temporary unlimited-key override used under explicit user authorization
   was removed after the price overrun.

## Commands Used

Focused verification and request-free endpoint checks:

```powershell
python -m py_compile scripts\run_managed_fidelity_benchmark.py tests\test_managed_fidelity_benchmark.py
python -m unittest tests.test_managed_fidelity_benchmark -v
@'
import json
from scripts import run_managed_fidelity_benchmark as b
print(json.dumps({name: b.fetch_endpoint_snapshot(name) for name in b.CANDIDATES}, indent=2))
'@ | python -
```

The three historical live commands used a temporary, explicitly authorized
`--allow-unlimited-key` gate. That flag is intentionally absent from the final
script. The key was loaded from the Windows user environment and was never
printed or written to project files:

```powershell
$env:OPENROUTER_API_KEY=[Environment]::GetEnvironmentVariable('OPENROUTER_API_KEY','User'); python scripts\run_managed_fidelity_benchmark.py --photo 'C:\Users\belou\Downloads\output\task37-visible-mark-acceptance-fixed\gemini-upstream-cleaned.png' --face 'C:\Users\belou\Downloads\output\task37-visible-mark-acceptance-fixed\gemini-owned-cleaned.png' --output-dir 'C:\Users\belou\Downloads\output\task41-managed-fidelity' --candidate seedream-4.5 --allow-paid --allow-unlimited-key
$env:OPENROUTER_API_KEY=[Environment]::GetEnvironmentVariable('OPENROUTER_API_KEY','User'); python scripts\run_managed_fidelity_benchmark.py --photo 'C:\Users\belou\Downloads\output\task37-visible-mark-acceptance-fixed\gemini-upstream-cleaned.png' --face 'C:\Users\belou\Downloads\output\task37-visible-mark-acceptance-fixed\gemini-owned-cleaned.png' --output-dir 'C:\Users\belou\Downloads\output\task41-managed-fidelity' --candidate seedream-4.5-rgb-defaults --allow-paid --allow-unlimited-key
$env:OPENROUTER_API_KEY=[Environment]::GetEnvironmentVariable('OPENROUTER_API_KEY','User'); python scripts\run_managed_fidelity_benchmark.py --photo 'C:\Users\belou\Downloads\output\task37-visible-mark-acceptance-fixed\gemini-upstream-cleaned.png' --face 'C:\Users\belou\Downloads\output\task37-visible-mark-acceptance-fixed\gemini-owned-cleaned.png' --output-dir 'C:\Users\belou\Downloads\output\task41-managed-fidelity' --candidate riverflow-v2.5-pro --allow-paid --allow-unlimited-key
```

Riverflow was analyzed from its preserved provider bytes after the cost gate
stopped the live report:

```powershell
python scripts\run_managed_fidelity_benchmark.py --photo 'C:\Users\belou\Downloads\output\task37-visible-mark-acceptance-fixed\gemini-upstream-cleaned.png' --face 'C:\Users\belou\Downloads\output\task37-visible-mark-acceptance-fixed\gemini-owned-cleaned.png' --output-dir 'C:\Users\belou\Downloads\output\task41-managed-fidelity' --candidate riverflow-v2.5-pro --existing-result 'C:\Users\belou\Downloads\output\task41-managed-fidelity\output-riverflow-v2.5-pro.provider'
```

## Verification

The final closed-gate state passes `28/28` focused Task 41 tests and all `136`
project tests. The offscreen `MainWindow` smoke check also passes. No build,
release, tag, installer, or GitHub Actions workflow was run.

## Sources

- [OpenRouter Image API and all-or-nothing billing](https://openrouter.ai/docs/guides/overview/multimodal/image-generation)
- [OpenRouter endpoint records](https://openrouter.ai/docs/api/api-reference/images/list-image-model-endpoints)
- [OpenRouter key limits](https://openrouter.ai/docs/api/reference/limits)
- [Seedream 4.5](https://seed.bytedance.com/en/seedream4_5)
- [Riverflow production editing](https://www.riverflow.ai/research/introducing-riverflow-2-0)
- [Google SynthID](https://deepmind.google/models/synthid/)
