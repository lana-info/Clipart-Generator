# Detailed Run Diagnostics Design

## Goal

Make the diagnostic journal explain the complete processing path for every
image so that a user or support person can identify the exact failed stage,
provider request and provider response without exposing prompts, credentials,
private paths or image contents.

## Scope

The change extends the existing `DiagnosticJournal`, per-run technical log and
diagnostic UI. It does not change generation, processing, retry, licensing or
update behavior. It does not make additional network requests and does not
enable paid provider probes.

The first implementation covers:

- KIE generation, upscale and background-removal requests;
- PhotoRoom background removal;
- RunPod task submission and polling;
- local image-processing stages already reported by the worker;
- input validation, provider upload, task creation, polling, result download,
  output validation and final save.

## Privacy and security boundary

The journal must never contain:

- prompt text, negative-prompt text or prompt fragments;
- API keys, licence keys, tokens, authorization headers or `.env` contents;
- request or response headers;
- full local paths or user-directory names;
- source or result image bytes, thumbnails or base64 data;
- uploaded, signed, temporary or result URLs;
- unfiltered raw HTTP response bodies.

Prompt diagnostics are limited to the row/item number, character count and
reference count. Image diagnostics contain metadata only: safe basename,
format, byte size, width, height, colour mode and alpha presence.

Provider responses are parsed at the network boundary and reduced to an
allowlisted structure before they can enter a Qt signal, run log or persistent
journal. Provider messages are bounded and passed through the existing secret
and path redaction.

## Event model

Every event uses the existing journal envelope and adds stable correlation
fields:

- `operation_id`: one launch or retry;
- `item_index` and `item_total`: one image or generated result;
- `attempt`: retry number for that item;
- `stage`: stable stage identifier;
- `provider` and `model` when an external service is involved;
- `outcome`: `started`, `succeeded`, `failed`, `cancelled` or `skipped`;
- `elapsed_ms` when a stage finishes;
- `correlation_id`: provider task identifier when available.

Detailed events include:

1. `item_input_inspected`: safe image metadata and prompt/reference counts.
2. `stage_started`: the exact local or remote stage and its non-secret
   parameters.
3. `provider_upload_started` / `provider_upload_finished`: provider, safe file
   metadata, HTTP status, uploaded byte count and elapsed time. No upload URL.
4. `provider_task_submitted`: provider, model, safe request parameters, HTTP
   status and task identifier.
5. `provider_task_polled`: poll number, HTTP status, provider state and elapsed
   time. Every poll is retained until the bounded journal limit is reached.
6. `provider_task_succeeded` / `provider_task_failed`: task identifier, final
   state, safe error code/message and result count.
7. `provider_result_downloaded`: result number, HTTP status, byte count,
   detected image metadata and elapsed time. No result URL.
8. `stage_finished`: stage outcome, output metadata and elapsed time.
9. `item_finished`: final item outcome and the failed stage when applicable.
10. `run_finished`: totals, duration, cancelled/failed/succeeded counts.

The existing human-readable progress messages remain unchanged. Structured
events are an additional channel and are not reconstructed from Russian UI
strings when the worker has the original data.

## Safe provider response summaries

### KIE

Allowed response fields are HTTP status, `taskId`, `state`, `failCode`, bounded
`failMsg`, polling attempt, result count and elapsed time. `resultJson` is parsed
only to count usable results; its URLs and raw JSON are discarded from
diagnostics.

### PhotoRoom

Allowed fields are HTTP status, response byte count, detected output format,
dimensions, colour mode, alpha presence and elapsed time. Binary response data
and headers are not logged.

### RunPod

Allowed fields are HTTP status, task identifier, provider status, bounded safe
error code/message, polling attempt, result count and elapsed time. Worker-
specific output payloads are not copied wholesale.

## Architecture

`provider_diagnostics.py` will own provider-neutral sanitization and event
construction. It accepts already parsed values and returns dictionaries made
only from declared fields. It has no network access and no Qt dependency.

`WorkerThread` will expose a structured diagnostic signal in addition to its
existing progress/error signals. Network and local-processing boundaries emit
events with the current item context. The worker must emit no event containing
raw request dictionaries because they may contain prompts, keys or URLs.

`RunQueueSession` will receive structured events, attach the authoritative run
and item identifiers, append a readable ordered line to the current technical
log and forward the sanitized event to `DiagnosticJournal`. Existing parsing
of legacy progress strings remains as a compatibility fallback.

`DiagnosticJournal` will expand its detail allowlist and schema to store the
new scalar metadata. Session storage remains bounded and private. The limits
will be increased to 8 MiB per session and 24 MiB total across the newest three
sessions so that a run of hundreds of items can retain provider polling events.

## User interface

The existing diagnostic window remains the single diagnostic entry point. It
adds:

- severity filter: all, warnings/errors, errors;
- source filter: all, KIE, PhotoRoom, RunPod, local processing;
- image/item selector populated from safe item numbers and basenames;
- an ordered event list showing time, image, stage and outcome;
- a details pane with Russian labels for image metadata, provider/model,
  parameters, task identifier, HTTP status, provider state, error and duration;
- the existing export action, now including the same structured details.

No exact prompt is shown and no option to include it is added. The diagnostic
window must remain usable at the application's 980 x 700 minimum through
internal scrolling rather than resizing the top-level application window.

## Error handling

Diagnostic recording is best-effort and must never fail the user's image job.
Malformed provider data produces a bounded `diagnostic_parse_failed` event
without the original body. If the journal cannot write to disk, it continues
using its existing bounded memory fallback. Reaching the storage limit keeps
the existing `log_truncated` marker.

## Verification

Automated tests must prove:

- exact image metadata and ordered stage/provider events are recorded;
- successful and failed KIE responses produce useful safe summaries;
- provider polling events retain order and correlation identifiers;
- prompt text, secrets, paths, headers, URLs and raw response bodies never
  appear in memory logs, journal files or exported ZIP files;
- malformed responses and journal write failures do not break processing;
- filtering and detail rendering work at 1400 x 900 and 980 x 700;
- existing generation, processing, retry and export behavior is unchanged.

No live or paid API request is required. Provider responses are represented by
deterministic local fixtures.

## Documentation

The human-readable API contract register will link each provider call to the
diagnostic event names emitted for it. Author documentation will explain how to
open the journal, select an image, identify the failed stage and export a safe
support package.
