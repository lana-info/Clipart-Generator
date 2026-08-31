# ADR-002: Fal.ai integration boundary and initial endpoint profiles

Status: Accepted for implementation in the 3.1 phase; amended 2026-08-31

## Decision

Fal.ai is integrated through a provider adapter that exposes queue primitives:
submit, status, result and cancel. The adapter stores and returns Fal's
`request_id`; it does not block the UI, silently switch to another paid model,
or download a result without an explicit higher-level run decision.

The first endpoint profiles to validate are:

- generation: a selected Fal image-generation endpoint, model ID kept in the
  model catalog rather than hard-coded in the UI;
- background removal: `fal-ai/bria/background/remove`;
- upscale: `fal-ai/esrgan`.

These profiles are candidates, not a claim that every endpoint has identical
inputs, pricing, retention, alpha behavior or cancellation guarantees. Each
endpoint must have its own capability record before appearing in a workflow.

## 2026-08-31 amendment: ESRGAN retirement

Windows acceptance testing rejected the visible quality of `fal-ai/esrgan`.
It is retired from both user-selectable upscale stages and from the current
cost estimate. Existing saved selections migrate to KIE before background
removal and Local Real-ESRGAN after background removal. Fal image generation
and Fal background removal remain available.

The ESRGAN adapter/profile may remain internally for recovery and compatibility
with already-recorded tasks, but must not appear as a new selectable operation.
Another paid Fal upscale requires separate endpoint validation and acceptance.

## Authentication and transport

The REST queue uses `https://queue.fal.run/{model_id}` with
`Authorization: Key {FAL_KEY}`. Status, result and cancel use the request URL
returned by the queue contract or its equivalent model/request path. Transport
is HTTPS-only and response sizes are bounded. On Windows, the desktop BYOK
key is stored separately using Windows DPAPI; KIE/PhotoRoom legacy `.env`
storage is not reused for Fal. A production gateway remains the preferred
architecture when the application is distributed beyond a trusted desktop.
On platforms without a protected local store, persistent Fal BYOK is rejected
instead of falling back to plaintext.

## Lifecycle and cancellation

The provider contract retains Fal's `IN_QUEUE`, `IN_PROGRESS` and `COMPLETED`
states and maps cancellation responses separately. A cancellation request is
not treated as proof that a running job stopped: the UI must be able to show
`cancel_requested`, `already_completed`, `cancel_failed` and
`completed_after_cancel` when the final observation requires it.

## Cost and retention

Pricing and media expiration are model-specific and must be shown as an
explicit estimate with timestamp and currency when available. A live smoke
test requires user approval and a budget limit. Results must be downloaded
before the provider's media expiration when the user chooses to keep them.

## Sources

- https://fal.ai/docs/documentation/model-apis/inference/queue
- https://fal.ai/models/fal-ai/bria/background/remove/api
- https://fal.ai/models/fal-ai/esrgan/api
