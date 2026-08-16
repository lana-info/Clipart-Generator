# V3 updates and diagnostics design

## Goal

Connect the shipped V3 desktop application to the existing self-hosted license
and release service, and add a user-facing diagnostic journal that is useful for
support without collecting secrets or growing without bounds.

The update flow is opt-in. The application checks once after a successful
startup license validation. It does not download anything until the user accepts
an explicit update prompt.

## Scope and delivery order

The work has two independently testable parts that share correlation IDs and
diagnostic events:

1. secure Windows update discovery, download, verification, and installer
   launch through the license service;
2. a persistent V3 diagnostic journal covering application, licensing,
   updates, configuration, and processing.

The diagnostic foundation is implemented first so the updater's first shipped
version records its own decisions and failures. Only `windows-x64` and the
`stable` channel are active. No macOS build or update path is added.

## Selected update approach

Use the license service as the authoritative update channel. Do not reconnect
the legacy public GitHub `version.json` flow.

The server already owns products, licenses, update-entitlement dates, signed
release manifests, and release metadata. Complete that boundary with private
artifact storage and short-lived download tokens. This is stronger than giving
the desktop client a permanent installer URL: withdrawing a release or denying
an update entitlement continues to have effect, and a copied URL is not a
durable public download link.

The desktop client contains only the update-signing public key. Server signing
keys, artifact storage paths, administrator credentials, and download-token
state remain server-side and outside Git.

## Server components

### Release administration

- An administrator creates a draft Windows release for product
  `clipart-generator`, channel `stable`, and a semantic version.
- The installer is uploaded to server-managed storage outside Git, or attached
  through an owner-controlled server-side import operation. A browser form must
  not accept an arbitrary local filesystem path.
- The server computes and stores the artifact filename, byte size, SHA-256, and
  update-signing metadata. Values supplied by a browser are not trusted as the
  computed result.
- Publication is a separate administrator action. Draft, withdrawn, deleted,
  malformed, or artifact-less releases are never returned to desktop clients.
- Existing release audit events are extended to cover artifact attachment,
  publication, withdrawal, and deletion without storing credentials or private
  paths.

### Manifest API

`POST /api/v1/releases/manifest` continues to require the activated device's
license ID, product ID, public device key, fresh nonce, and proof. The server:

1. validates the device and active license;
2. checks `updates_until` independently from the normal license expiry;
3. selects published `stable` releases for `windows-x64`;
4. returns a bounded Ed25519-signed envelope using the dedicated update key.

Each release entry contains only bounded public metadata: semantic version,
platform, channel, release notes, artifact filename, size, SHA-256, publication
time, and a short-lived HTTPS download URL. The manifest does not expose a
server storage path or permanent origin URL.

### Artifact download

- The download URL contains a cryptographically random, short-lived opaque
  token stored only as a hash on the server.
- A token is bound to the eligible license, activation, artifact, and expiry.
- Download responses have a fixed maximum size, safe content type, safe
  filename, and no path disclosure.
- Tokens allow a small bounded number of requests so ordinary HTTP behavior
  does not make a valid download fail, but they cannot become permanent links.
- Withdrawn/deleted releases and expired or revoked entitlements fail closed.
- Partial uploads and temporary download files are cleaned safely.

## Desktop update flow

### Discovery

- After the saved license has been validated online and the V3 main window is
  visible, a background worker performs one update check per application
  launch. It never blocks the UI thread.
- The request uses the same device proof mechanism as licensing but verifies
  the response with the separate pinned update public key and expected key ID.
- The client validates the envelope, product, platform, stable channel,
  semantic versions, HTTPS download URL, filename, size, SHA-256, and response
  bounds. It selects the greatest eligible semantic version rather than
  trusting server list order.
- No update prompt is shown when the current version is latest. A check failure
  is recorded in diagnostics but does not invalidate an already successful
  license check or block normal work.

### User consent and download

For a newer version, show one clear prompt:

> Доступна версия {version}. Обновить программу сейчас?
>
> Программа скачает обновление, закроется и запустит установщик.

- `Обновить` starts the download.
- `Не сейчас` closes the prompt and downloads nothing. The application asks
  again on the next launch if the release is still current.
- The download dialog shows version, progress, received/total size, and a
  `Отмена` action. Cancellation deletes the partial file and keeps the
  application open.
- The installer is written atomically to the per-user temporary/application
  data area, never to `Program Files`, the working image folder, or the process
  directory.

### Verification and installation

Before launch, the client verifies:

- the final byte count equals the signed manifest size;
- SHA-256 equals the signed manifest digest;
- the manifest's Ed25519 signature is valid under the pinned update key;
- the file remains the same verified file when it is launched.

Any mismatch deletes the file, records a bounded error, and leaves the current
application running. On success, the application launches the Windows
installer, then exits cleanly. There is no silent installation, background
installation, or automatic download after `Не сейчас`.

On the next launch, stale partial files and obsolete downloaded installers are
removed. Resume support and mandatory/forced updates are intentionally out of
scope for this version.

## Diagnostic journal

### Storage and retention

- Store one UTF-8 JSON Lines session file per application launch under the
  per-user Clipart Generator data directory.
- Retain the newest three launch sessions with a hard total limit of 10 MiB.
- Limit each individual event to 16 KiB and the active session to 4 MiB. If the
  active session reaches its limit, stop writing repeated detail, write one
  `log_truncated` marker when possible, and preserve an in-memory aggregate for
  the final session summary.
- Do not log progress ticks. For large batches, record the operation plus one
  terminal result per item and aggregate counts, which keeps a 100-image run
  useful without producing thousands of low-value entries.
- Writes are serialized and flushed at meaningful boundaries. A damaged final
  line after a crash does not prevent earlier records or other sessions from
  opening.

### Event model

Every event has:

- schema version, UTC timestamp, severity, event name, safe Russian summary;
- launch/session ID and, where applicable, operation/correlation ID;
- application version, platform, screen/stage, outcome, and retry state;
- bounded structured details chosen from an allowlist.

Record at least:

- application start, successful UI readiness, normal exit, and unhandled
  exception;
- license activation/validation outcome and server correlation ID, never the
  key, device private key, proof, or reusable authorization data;
- update check, available/current version, user decision, download progress
  milestones, verification result, cancellation, installer launch, and errors;
- mode selection, project start/continue, and output-folder validation using a
  role plus safe basename instead of a full personal path;
- API settings save as provider/configuration presence only, never API-key
  values;
- generation/processing operation start, per-item terminal outcome, retry,
  cancellation, final counts, safe provider/task/model identifiers, and bounded
  error codes/messages;
- report or diagnostic export success/failure.

Raw provider responses, prompts, generated images, license keys, API keys,
device secrets, environment variables, database data, and complete personal
paths are prohibited. Tracebacks retain exception type, module basename,
function, and line number while removing full filesystem paths and secret-like
values.

### User interface

- Add one `Журнал диагностики` action beside license and API settings on the
  initial mode-selection screen and in the shared wizard header, so it remains
  available before and during work.
- Open a single journal window showing the newest events first, with local
  display time, severity, operation, and a plain-language summary. Technical
  fields are expandable rather than always filling the screen.
- Provide only two primary support actions:
  - `Скопировать запись` copies the selected sanitized event in readable text;
  - `Экспортировать диагностику` creates one ZIP containing readable TXT,
    structured JSON, a safe system/application summary, and a short README.
- The export dialog states that keys, prompts, images, and full paths are not
  included. Exporting never deletes the journal.
- The existing per-run `Технический лог` and report export may remain for run
  results, but the new journal is the authoritative cross-launch support view.

## Failure handling

- Journal failure must never crash or block the application. It falls back to
  an in-memory bounded buffer and shows an export error only when the user asks
  to export.
- Update service failure does not start a download and does not block an
  already licensed application session.
- An invalid signed manifest, unsafe URL, oversized response/artifact,
  checksum mismatch, storage error, timeout, cancellation, or installer launch
  failure produces a safe diagnostic event and a concise Russian message when
  user action is affected.
- Concurrent update checks and downloads are rejected so only one updater job
  can exist per process.

## Verification

### Server tests

- entitlement, product, device, platform, channel, and publication filtering;
- signed manifest acceptance and rejection after tampering;
- semantic release metadata validation and bounded response sizes;
- upload/import size limits, computed SHA-256, atomic storage, and path
  containment;
- token entropy, hashing, binding, expiry, bounded use, withdrawal, revocation,
  and download size/content headers;
- audit records contain no keys, tokens, or private storage paths.

### Desktop tests

- one asynchronous check after licensed V3 startup and no legacy updater call;
- no download before `Обновить`, including after `Не сейчас`;
- valid manifest selection and rejection of bad signatures, claims, semantic
  versions, URLs, sizes, hashes, and oversized responses;
- progress/cancel behavior, atomic temporary file, checksum verification,
  installer launch, and cleanup;
- no UI freeze and no update activity when startup licensing fails;
- three-session/10 MiB retention, truncated/corrupt-line recovery, concurrent
  writes, event allowlist, and secret/path redaction;
- journal availability on both initial selection and wizard screens;
- copy and ZIP export contents, readability, and absence of prohibited data;
- regression coverage for all three V3 modes and packaged-entrypoint smoke.

### Release acceptance

- Run both repository test suites and desktop packaged smoke checks.
- Deploy server changes only under a separate explicit production-deployment
  authorization, then validate with a non-customer test license and draft test
  release.
- Build a new Windows installer only under a separate explicit build command.
- Publish a real update revision only after the newly built client is manually
  installed and its update UI, cancellation, download, verification, and
  installer handoff are verified on Windows.

## Explicit non-goals

- macOS or Linux installers;
- silent, forced, or scheduled background updates;
- update checks repeated during one application launch;
- log upload to the server, telemetry, screenshots, generated-file attachment,
  or remote support access;
- automatic sending of a diagnostic package;
- changing license business terms or allowing offline application use.
